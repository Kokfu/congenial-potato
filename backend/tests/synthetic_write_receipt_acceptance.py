"""Fixture-only durable acceptance for signed private-ledger receipts."""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import (AuditEvent, SyntheticWriteAdmission,
    SyntheticWriteLedgerControl, SyntheticWriteReceipt, now)
from workforce.synthetic_write_contract import (WriteContractError, intent_digest,
    verify_write_receipt)
from synthetic_write_admission import (_authority, _enabled, _locked)
from workforce.tool_approval import _digest


class SyntheticWriteReceiptDenied(WriteContractError):
    pass


@dataclass(frozen=True)
class AcceptedSyntheticWriteReceipt:
    invocation_id: str
    receipt_sha256: str
    result_revision: int
    event_id: str
    accepted_at: datetime
    trust_origin: str = 'synthetic_write'


def _view(row, receipt):
    return AcceptedSyntheticWriteReceipt(row.invocation_id, row.receipt_sha256,
        receipt.result_revision, str(receipt.event_id), row.accepted_at)


def accept_synthetic_write_receipt(invocation_id, intent, envelope, *, key: bytes,
        experiment_enabled=False):
    """Persist one exact receipt under current authority; duplicates are history."""
    _enabled(experiment_enabled)
    if type(key) is not bytes or len(key) != 32:
        raise SyntheticWriteReceiptDenied('Private synthetic write key unavailable')
    if type(envelope) is not str:
        raise SyntheticWriteReceiptDenied('Signed synthetic receipt unavailable')
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, invocation_id)
        admission = db.scalar(select(SyntheticWriteAdmission).where(
            SyntheticWriteAdmission.invocation_id == invocation_id).with_for_update()
            .execution_options(populate_existing=True))
        if admission is None or approval is None:
            raise SyntheticWriteReceiptDenied('Consumed synthetic admission unavailable')
        try:
            receipt = verify_write_receipt(envelope, intent, key=key)
        except WriteContractError as exc:
            raise SyntheticWriteReceiptDenied('Signed synthetic receipt unavailable') from exc
        document = receipt.model_dump(mode='json')
        receipt_hash = _digest(document)
        expected_ledger = db.scalar(select(SyntheticWriteLedgerControl).where(
            SyntheticWriteLedgerControl.id == 1).with_for_update())
        if (expected_ledger is None or admission.ledger_id != expected_ledger.ledger_id or
                admission.intent_sha256 != intent_digest(intent) or
                admission.record_id != str(intent.record_id) or
                admission.expected_revision != intent.expected_revision or
                admission.project_id != invocation.project_id or
                admission.agent_id != source.agent_id or admission.root_id != source.root_id or
                admission.approval_id != approval.id or
                admission.approval_payload_sha256 != approval.payload_hash or
                admission.policy_snapshot_sha256 != _digest(invocation.policy_snapshot)):
            raise SyntheticWriteReceiptDenied('Receipt differs from consumed synthetic admission')
        previous = db.get(SyntheticWriteReceipt, invocation_id)
        if previous is not None:
            if (previous.receipt_sha256 != receipt_hash or previous.receipt != document or
                    previous.trust_origin != 'synthetic_write'):
                raise SyntheticWriteReceiptDenied('Recorded synthetic receipt identity unavailable')
            return _view(previous, receipt)
        reason = _authority(db, invocation, source, root, approval)
        if reason:
            raise SyntheticWriteReceiptDenied('Synthetic write authority unavailable: '+reason)
        row = SyntheticWriteReceipt(invocation_id=invocation_id,
            receipt_sha256=receipt_hash, receipt=document,
            trust_origin='synthetic_write', accepted_at=now())
        db.add(row)
        db.add(AuditEvent(actor='synthetic-write-receipt-fixture',
            action='synthetic.write.receipt', resource=invocation_id,
            outcome='accepted', detail={'receipt_sha256': receipt_hash}))
        db.commit()
        return _view(row, receipt)
