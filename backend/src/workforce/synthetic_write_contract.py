"""Inert fixture metadata only: no authority, ledger mutation or retry permission.

A signature authenticates a fixture key holder, never external execution truth.
Current approval/grant/budget/cancellation and consumed admission are separate gates.
"""
from datetime import datetime, timezone
import hashlib
import hmac
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .reviewed_runner_contract import _StrictModel, _canonical, _parse, _utc

MAX_WRITE_BYTES = 4096
MAX_DOCUMENT_BYTES = 8192
_RECEIPT_DOMAIN = b'workforce.synthetic.write.receipt.v1\0'
_RECONCILIATION_DOMAIN = b'workforce.synthetic.write.reconciliation.v1\0'


class WriteContractError(ValueError):
    pass


def _integer_version(value):
    if type(value) is not int:
        raise ValueError('Write version must be an integer')
    return value


class WriteScope(_StrictModel):
    project_id: UUID
    agent_id: UUID
    root_id: UUID
    invocation_id: UUID


class SyntheticWriteIntent(_StrictModel):
    version: Literal[1]
    action: Literal['synthetic.record.replace']
    scope: WriteScope
    ledger_id: UUID
    record_id: UUID
    expected_revision: int = Field(ge=0, le=2147483646)
    content_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    content_size: int = Field(ge=0, le=MAX_WRITE_BYTES)
    approval_payload_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    policy_snapshot_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    _version = field_validator('version', mode='before')(_integer_version)


class AppliedWriteReceipt(_StrictModel):
    version: Literal[1]
    trust_origin: Literal['synthetic_write']
    intent_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    event_id: UUID
    applied_at: datetime
    result_revision: int = Field(ge=1, le=2147483647)
    content_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    content_size: int = Field(ge=0, le=MAX_WRITE_BYTES)

    _version = field_validator('version', mode='before')(_integer_version)

    @field_validator('applied_at')
    @classmethod
    def aware_timestamp(cls, value):
        return _utc(value)


class ReconciliationQuery(_StrictModel):
    version: Literal[1]
    intent_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    nonce: UUID
    issued_at: datetime

    _version = field_validator('version', mode='before')(_integer_version)

    @field_validator('issued_at')
    @classmethod
    def aware_timestamp(cls, value):
        return _utc(value)


class ReconciliationResult(_StrictModel):
    version: Literal[1]
    trust_origin: Literal['synthetic_write']
    query: ReconciliationQuery
    outcome: Literal['applied', 'not_applied', 'unknown']
    observed_at: datetime
    receipt: AppliedWriteReceipt | None

    _version = field_validator('version', mode='before')(_integer_version)

    @field_validator('observed_at')
    @classmethod
    def aware_timestamp(cls, value):
        return _utc(value)

    @model_validator(mode='after')
    def evidence(self):
        if ((self.outcome == 'applied') != (self.receipt is not None) or
                self.observed_at < self.query.issued_at or
                (self.receipt is not None and (self.receipt.intent_sha256 != self.query.intent_sha256
                    or self.receipt.applied_at > self.observed_at))):
            raise ValueError('Reconciliation evidence unavailable')
        return self


class _ReceiptEnvelope(_StrictModel):
    receipt: AppliedWriteReceipt
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')


class _ReconciliationEnvelope(_StrictModel):
    result: ReconciliationResult
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')


def _parse_document(raw, model):
    try:
        if (type(raw) is not str or not 0 < len(raw) <= MAX_DOCUMENT_BYTES
                or len(raw.encode('utf-8')) > MAX_DOCUMENT_BYTES):
            raise ValueError('Write document exceeds bound')
        return _parse(raw, model)
    except (ValueError, TypeError, RecursionError):
        raise WriteContractError('Synthetic write document unavailable') from None


def _validated(value, model):
    try:
        return model.model_validate(value)
    except (ValueError, TypeError):
        raise WriteContractError('Synthetic write identity unavailable') from None


def parse_write_intent(raw: str) -> SyntheticWriteIntent:
    """Shape only. Supplied approval/policy hashes establish no DB authorization."""
    return _parse_document(raw, SyntheticWriteIntent)


def intent_digest(intent: SyntheticWriteIntent) -> str:
    value = _validated(intent, SyntheticWriteIntent)
    return hashlib.sha256(_canonical(value.model_dump(mode='json')).encode('utf-8')).hexdigest()


def _key(key):
    if type(key) is not bytes or len(key) != 32:
        raise WriteContractError('Private synthetic write key unavailable')
    return key


def _wire(value, domain):
    return domain+_canonical(value.model_dump(mode='json')).encode('utf-8')


def _receipt_bound(receipt, intent):
    intent = _validated(intent, SyntheticWriteIntent)
    if (receipt.intent_sha256 != intent_digest(intent) or
            receipt.result_revision != intent.expected_revision+1 or
            receipt.content_sha256 != intent.content_sha256 or receipt.content_size != intent.content_size or
            receipt.applied_at > datetime.now(timezone.utc)):
        raise WriteContractError('Synthetic write receipt binding unavailable')


def sign_write_receipt(raw: str, intent: SyntheticWriteIntent, *, key: bytes,
                       experiment_enabled=False) -> str:
    if experiment_enabled is not True:
        raise WriteContractError('Synthetic write signing disabled')
    receipt = _parse_document(raw, AppliedWriteReceipt)
    _receipt_bound(receipt, intent)
    signature = hmac.digest(_key(key), _wire(receipt, _RECEIPT_DOMAIN), 'sha256').hex()
    return _ReceiptEnvelope(receipt=receipt, signature=signature).model_dump_json()


def verify_write_receipt(raw: str, intent: SyntheticWriteIntent, *, key: bytes) -> AppliedWriteReceipt:
    envelope = _parse_document(raw, _ReceiptEnvelope)
    if not hmac.compare_digest(envelope.signature,
            hmac.digest(_key(key), _wire(envelope.receipt, _RECEIPT_DOMAIN), 'sha256').hex()):
        raise WriteContractError('Synthetic write signature unavailable')
    _receipt_bound(envelope.receipt, intent)
    return envelope.receipt


def parse_reconciliation_query(raw: str, intent: SyntheticWriteIntent) -> ReconciliationQuery:
    query = _parse_document(raw, ReconciliationQuery)
    if query.intent_sha256 != intent_digest(intent) or query.issued_at > datetime.now(timezone.utc):
        raise WriteContractError('Synthetic reconciliation query unavailable')
    return query


def _result_bound(result, query, intent):
    query = _validated(query, ReconciliationQuery)
    if (query.intent_sha256 != intent_digest(intent) or result.query != query or
            result.observed_at > datetime.now(timezone.utc)):
        raise WriteContractError('Synthetic reconciliation binding unavailable')
    if result.receipt is not None:
        _receipt_bound(result.receipt, intent)


def sign_reconciliation_result(raw: str, query: ReconciliationQuery,
        intent: SyntheticWriteIntent, *, key: bytes, experiment_enabled=False) -> str:
    if experiment_enabled is not True:
        raise WriteContractError('Synthetic write signing disabled')
    result = _parse_document(raw, ReconciliationResult)
    _result_bound(result, query, intent)
    signature = hmac.digest(_key(key), _wire(result, _RECONCILIATION_DOMAIN), 'sha256').hex()
    return _ReconciliationEnvelope(result=result, signature=signature).model_dump_json()


def verify_reconciliation_result(raw: str, query: ReconciliationQuery,
        intent: SyntheticWriteIntent, *, key: bytes) -> ReconciliationResult:
    """Authenticate fixture evidence only; no outcome grants write/retry permission."""
    envelope = _parse_document(raw, _ReconciliationEnvelope)
    if not hmac.compare_digest(envelope.signature,
            hmac.digest(_key(key), _wire(envelope.result, _RECONCILIATION_DOMAIN), 'sha256').hex()):
        raise WriteContractError('Synthetic reconciliation signature unavailable')
    _result_bound(envelope.result, query, intent)
    return envelope.result
