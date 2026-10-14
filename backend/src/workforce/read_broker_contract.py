"""Exact single-use broker contract experiment; no server or product dispatch.

Only a trusted mediator holding the key can attest a ticket. This module does
not look up database authority: the later issuer must bind a committed attempt
and recheck authority before issuance and after the response.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import stat
from typing import Callable, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .local_read_experiment import ReadDenied, ReadRequest, ReadResult
from .network_policy import (PinnedDestination, PublicReadGrant,
                             canonical_public_url, execute_public_read_experiment)

MAX_ENVELOPE_BYTES = 16384
MAX_TICKET_LIFETIME = timedelta(seconds=30)


class BrokerOutcomeUnknown(ReadDenied):
    """The broker fence exists; dispatch must not be repeated."""


class BrokerReadTicket(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: Literal[1] = 1
    attempt_id: UUID
    approval_id: UUID
    project_id: UUID
    agent_id: UUID
    root_id: UUID
    payload_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    policy_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    schema_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    grant_id: UUID
    grant_revision: int = Field(ge=1, strict=True)
    grant_expires_at: datetime
    issued_at: datetime
    expires_at: datetime
    url: str = Field(min_length=1, max_length=2048)
    max_bytes: int = Field(ge=1, le=65536, strict=True)
    timeout_seconds: float = Field(gt=0, le=5, strict=True)
    addresses: tuple[str, ...] = Field(min_length=1, max_length=64)

    @field_validator('version', mode='before')
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('Broker version unavailable')
        return value

    @model_validator(mode='after')
    def exact_destination_and_time(self):
        canonical_public_url(self.url)
        normalized = []
        for value in self.addresses:
            address = ipaddress.ip_address(value)
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                address = address.ipv4_mapped
            if not address.is_global or '%' in value:
                raise ValueError('Broker destination is not public')
            normalized.append(str(address))
        if tuple(sorted(set(normalized))) != self.addresses:
            raise ValueError('Broker address set is not canonical')
        if any(value.tzinfo is None or value.utcoffset() is None for value in (
                self.issued_at, self.expires_at, self.grant_expires_at)):
            raise ValueError('Broker timestamp lacks timezone')
        if (not timedelta(0) < self.expires_at - self.issued_at <= MAX_TICKET_LIFETIME or
                self.expires_at > self.grant_expires_at):
            raise ValueError('Broker ticket lifetime unavailable')
        return self

    def current(self):
        at = datetime.now(timezone.utc)
        if self.issued_at > at or self.expires_at <= at or self.grant_expires_at <= at:
            raise ReadDenied('Broker ticket unavailable or expired')

    def request(self) -> ReadRequest:
        return ReadRequest(project_id=str(self.project_id), agent_id=str(self.agent_id),
            url=self.url, max_bytes=self.max_bytes,
            timeout_seconds=min(self.timeout_seconds,
                (self.expires_at - datetime.now(timezone.utc)).total_seconds()))


class _Envelope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ticket: BrokerReadTicket
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')


def _canonical(ticket: BrokerReadTicket) -> bytes:
    return json.dumps(ticket.model_dump(mode='json'), sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _key(key: bytes):
    if not isinstance(key, bytes) or len(key) != 32:
        raise ReadDenied('Broker key unavailable')


def sign_ticket(ticket: BrokerReadTicket, *, key: bytes) -> str:
    _key(key)
    # Revalidate even a trusted caller's model_copy/model_construct value.
    checked = BrokerReadTicket.model_validate(ticket.model_dump(mode='json'))
    checked.current()
    signature = hmac.digest(key, _canonical(checked), 'sha256').hex()
    envelope = _Envelope(ticket=checked, signature=signature).model_dump_json()
    if len(envelope.encode()) > MAX_ENVELOPE_BYTES:
        raise ReadDenied('Broker ticket exceeds size limit')
    return envelope


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReadDenied('Broker ticket contains duplicate fields')
        result[key] = value
    return result


def verify_ticket(envelope: str, *, key: bytes) -> BrokerReadTicket:
    _key(key)
    if not isinstance(envelope, str) or len(envelope.encode()) > MAX_ENVELOPE_BYTES:
        raise ReadDenied('Broker ticket unavailable')
    try:
        parsed = _Envelope.model_validate(json.loads(envelope, object_pairs_hook=_unique_object))
    except (ValueError, ValidationError, TypeError, RecursionError) as exc:
        raise ReadDenied('Broker ticket unavailable') from exc
    expected = hmac.digest(key, _canonical(parsed.ticket), 'sha256').hex()
    if not hmac.compare_digest(expected, parsed.signature):
        raise ReadDenied('Broker ticket unavailable')
    parsed.ticket.current()
    return parsed.ticket


def consume_ticket(ticket: BrokerReadTicket, *, journal: Path) -> None:
    """Commit an exclusive fence before effect. Never remove/reset on failure.

    The configured directory is trusted private storage; model input never
    selects its path. Each fence contains a digest only, never fetched content.
    """
    directory = None
    try:
        directory = os.open(journal, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(directory)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or
                stat.S_IMODE(info.st_mode) & 0o077):
            raise ReadDenied('Broker journal must be private and owned by broker')
        name = f'{ticket.attempt_id.hex}.attempt'
        try:
            marker = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        except FileExistsError as exc:
            raise BrokerOutcomeUnknown('Broker attempt already exists; no retry') from exc
        with os.fdopen(marker, 'wb') as stream:
            stream.write(hashlib.sha256(_canonical(ticket)).hexdigest().encode() + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)
    except OSError as exc:
        raise ReadDenied('Broker attempt could not be persisted') from exc
    finally:
        if directory is not None:
            os.close(directory)


def execute_broker_read(envelope: str, *, key: bytes, journal: Path,
                        resolver, connection_factory, experiment_enabled: bool = False,
                        after_fence: Callable | None = None) -> ReadResult:
    if not experiment_enabled or resolver is None or connection_factory is None:
        raise ReadDenied('Broker experiment is disabled or uninjected')
    ticket = verify_ticket(envelope, key=key)
    consume_ticket(ticket, journal=journal)
    if after_fence:
        after_fence()
    ticket.current()
    request = ticket.request()
    host, port = canonical_public_url(ticket.url)
    grant = PublicReadGrant(project_id=str(ticket.project_id), agent_id=str(ticket.agent_id),
        host=host, expires_at=min(ticket.expires_at, ticket.grant_expires_at))
    prepared = PinnedDestination(host=host, port=port, addresses=ticket.addresses)
    result = execute_public_read_experiment(request, grant, prepared,
        experiment_enabled=True, resolver=resolver, connection_factory=connection_factory)
    ticket.current()
    return result  # transient only; mediator must still perform post-effect authority checks
