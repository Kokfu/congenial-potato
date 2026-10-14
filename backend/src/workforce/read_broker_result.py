"""Authenticated transient broker replies; no database or product dispatch.

The shared key and caller-provided authority callback are trusted configuration.
Reply authentication attests broker output, never the truth of fetched claims.
"""
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
from typing import Callable, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic import BaseModel

from .local_read_experiment import ReadDenied, ReadResult
from .read_broker_contract import (_key, _unique_object, execute_broker_read,
                                   verify_ticket)

MAX_REPLY_BYTES = 6 * 65536 + 16384  # UTF-8 text can expand to JSON escapes.
_REPLY_DOMAIN = b'workforce.read.result.v1\0'


class BrokerResult(ReadResult):
    model_config = ConfigDict(extra='forbid', frozen=True)
    url: str = Field(strict=True, min_length=1, max_length=2048)
    media_type: Literal['text/plain', 'text/html']
    size: int = Field(strict=True, ge=0, le=65536)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    text: str = Field(strict=True, max_length=65536)
    trust_origin: Literal['external_claim'] = 'external_claim'

    @model_validator(mode='after')
    def provenance(self):
        body = self.text.encode('utf-8')
        if (self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None or
                self.size != len(body) or
                self.sha256 != hashlib.sha256(body).hexdigest()):
            raise ValueError('Broker result provenance unavailable')
        return self


class BrokerReply(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: Literal[1] = 1
    ticket_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    attempt_id: UUID
    result: BrokerResult

    @field_validator('version', mode='before')
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('Broker reply version unavailable')
        return value


class _ReplyEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reply: BrokerReply
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')


def ticket_digest(envelope: str) -> str:
    return hashlib.sha256(envelope.encode('utf-8')).hexdigest()


def _canonical(reply: BrokerReply) -> bytes:
    return _REPLY_DOMAIN + json.dumps(reply.model_dump(mode='json'), sort_keys=True,
                                      separators=(',', ':')).encode('utf-8')


def _bound(reply, ticket, envelope):
    at = datetime.now(timezone.utc)
    if (reply.attempt_id != ticket.attempt_id or
            reply.ticket_hash != ticket_digest(envelope) or
            reply.result.url != ticket.url or reply.result.size > ticket.max_bytes or
            not ticket.issued_at <= reply.result.retrieved_at <= min(at, ticket.expires_at)):
        raise ReadDenied('Broker result does not match issued ticket')


def sign_broker_reply(result: ReadResult, envelope: str, *, key: bytes) -> str:
    ticket = verify_ticket(envelope, key=key)
    try:
        reply = BrokerReply(ticket_hash=ticket_digest(envelope), attempt_id=ticket.attempt_id,
                            result=BrokerResult.model_validate(result.model_dump(mode='json')))
        _bound(reply, ticket, envelope)
        signed = _ReplyEnvelope(reply=reply,
            signature=hmac.digest(key, _canonical(reply), 'sha256').hex()).model_dump_json()
        if len(signed.encode()) > MAX_REPLY_BYTES:
            raise ReadDenied('Broker reply exceeds size limit')
        return signed
    except (ValueError, ValidationError, TypeError) as exc:
        raise ReadDenied('Broker result unavailable') from exc


def verify_broker_reply(signed: str, envelope: str, *, key: bytes) -> BrokerResult:
    _key(key)
    ticket = verify_ticket(envelope, key=key)
    try:
        if not isinstance(signed, str) or len(signed.encode()) > MAX_REPLY_BYTES:
            raise ReadDenied('Broker reply exceeds size limit')
        parsed = _ReplyEnvelope.model_validate(json.loads(signed, object_pairs_hook=_unique_object))
        expected = hmac.digest(key, _canonical(parsed.reply), 'sha256').hex()
        if not hmac.compare_digest(expected, parsed.signature):
            raise ReadDenied('Broker reply authentication unavailable')
        _bound(parsed.reply, ticket, envelope)
        return parsed.reply.result
    except (ValueError, ValidationError, TypeError, RecursionError) as exc:
        raise ReadDenied('Broker reply unavailable') from exc


def execute_authenticated_broker_read(envelope: str, *, key: bytes, journal: Path,
        authorize: Callable[[str], None], resolver, connection_factory,
        experiment_enabled: bool = False, after_fetch: Callable | None = None) -> str:
    """Trusted local harness only; the mandatory authorizer runs after fencing.

    It must check current mediator authority. No result/journal body is retained
    if response delivery is lost, and the consumed attempt is never retried.
    """
    if not experiment_enabled or not callable(authorize):
        raise ReadDenied('Authenticated broker experiment is disabled or uninjected')
    result = execute_broker_read(envelope, key=key, journal=journal,
        resolver=resolver, connection_factory=connection_factory, experiment_enabled=True,
        after_fence=lambda: authorize(envelope))
    if after_fetch:
        after_fetch()
    return sign_broker_reply(result, envelope, key=key)
