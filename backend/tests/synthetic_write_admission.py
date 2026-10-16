"""Fixture-only database admission before the private synthetic write ledger.

No product route imports this module. Admission presence consumes both the
invocation and its target revision in PostgreSQL; SQLite state cannot restore it.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import secrets
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from workforce.db import session_factory
from workforce.models import (Agent, Approval, ArtifactVersion, AuditEvent, BudgetAccount, Execution,
    SyntheticWriteAdmission, SyntheticWriteLedgerControl, ToolInvocation, now)
from workforce.synthetic_write_contract import (SyntheticWriteIntent, WriteContractError,
    intent_digest)
from synthetic_write_ledger import SyntheticWriteLedger
from workforce.tool_approval import _digest, _invalid_reason, exact_payload


class SyntheticWriteAdmissionDenied(WriteContractError):
    pass


class SyntheticWriteAdmissionUnknown(WriteContractError):
    pass


@dataclass(frozen=True)
class _Permit:
    invocation_id: str
    intent_sha256: str
    capability: bytes = field(repr=False)


def _enabled(value):
    if value is not True:
        raise SyntheticWriteAdmissionDenied('Synthetic write admission disabled')


def _locked(db, invocation_id):
    try:
        if type(invocation_id) is not str or str(UUID(invocation_id)) != invocation_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise SyntheticWriteAdmissionDenied('Synthetic write identity unavailable') from None
    hint = db.get(ToolInvocation, invocation_id)
    if hint is None or hint.action != 'project.artifact.write':
        raise SyntheticWriteAdmissionDenied('Approved synthetic write unavailable')
    source = db.get(Execution, hint.execution_id)
    if source is None:
        raise SyntheticWriteAdmissionDenied('Synthetic write source unavailable')
    root = db.scalar(select(Execution).where(Execution.id == source.root_id)
        .with_for_update().execution_options(populate_existing=True))
    db.refresh(source)
    invocation = db.scalar(select(ToolInvocation).where(ToolInvocation.id == invocation_id)
        .with_for_update().execution_options(populate_existing=True))
    approval = db.scalar(select(Approval).where(Approval.tool_invocation_id == invocation_id)
        .with_for_update().execution_options(populate_existing=True))
    return invocation, source, root, approval


def _authority(db, invocation, source, root, approval):
    if (root is None or root.id != source.root_id or root.cancelled or
            source.root_id != root.id):
        return 'root_or_cancellation_unavailable'
    if (invocation.status != 'admitted' or invocation.effect != 'write' or
            invocation.policy_decision != 'require_approval'):
        return 'invocation_unavailable'
    agent = db.scalar(select(Agent).where(Agent.id == source.agent_id)
        .with_for_update().execution_options(populate_existing=True))
    if agent is None or agent.status != 'active':
        return 'agent_unavailable'
    if (approval is None or approval.status != 'approved' or
            approval.decision_payload_hash != approval.payload_hash):
        return 'approval_unavailable'
    # Freeze policy inserts/updates until the local fixture effect completes;
    # row locks alone cannot protect a newly inserted exact-resource deny rule.
    db.execute(text('LOCK TABLE policy_rules IN SHARE MODE'))
    reason = _invalid_reason(db, invocation, approval, source)
    if reason:
        return reason
    account = db.scalar(select(BudgetAccount).where(BudgetAccount.root_id == root.id)
        .with_for_update().execution_options(populate_existing=True))
    if (account is None or account.currency != 'USD' or account.cap < 0 or
            account.spent < 0 or account.reserved < 0 or
            account.cap-account.spent-account.reserved <= 0):
        return 'root_budget_unavailable'
    return None


def _bound_intent(db, intent, invocation, source, approval, *, ledger_id):
    if type(intent) is not SyntheticWriteIntent:
        raise SyntheticWriteAdmissionDenied('Exact synthetic write intent required')
    digest = intent_digest(intent)  # revalidate copied models
    args = invocation.arguments
    try:
        record_id = str(UUID(args['artifact_id']))
        parent_id = args['expected_parent']
        if parent_id is None:
            expected_revision = 0
        else:
            parent = db.get(ArtifactVersion, parent_id)
            if (parent is None or parent.project_id != invocation.project_id or
                    parent.artifact_id != record_id):
                raise ValueError('Approved parent unavailable')
            expected_revision = parent.version
        content = args['content'].encode('utf-8')
    except (KeyError, TypeError, UnicodeError, ValueError):
        raise SyntheticWriteAdmissionDenied('Approved write payload unavailable') from None
    scope = intent.scope
    if (str(scope.invocation_id) != invocation.id or
            str(scope.project_id) != invocation.project_id or
            str(scope.agent_id) != source.agent_id or str(scope.root_id) != source.root_id or
            str(intent.ledger_id) != ledger_id or str(intent.record_id) != record_id or
            intent.expected_revision != expected_revision or
            intent.content_sha256 != hashlib.sha256(content).hexdigest() or
            intent.content_size != len(content) or
            intent.approval_payload_sha256 != approval.payload_hash or
            intent.approval_payload_sha256 != _digest(exact_payload(invocation)) or
            intent.policy_snapshot_sha256 != _digest(invocation.policy_snapshot)):
        raise SyntheticWriteAdmissionDenied('Synthetic intent differs from current approved write')
    return digest, content


def _lock_ledger_identity(db, ledger_id):
    db.execute(insert(SyntheticWriteLedgerControl).values(id=1, ledger_id=ledger_id,
        created_at=now()).on_conflict_do_nothing(index_elements=['id']))
    row = db.scalar(select(SyntheticWriteLedgerControl).where(
        SyntheticWriteLedgerControl.id == 1).with_for_update()
        .execution_options(populate_existing=True))
    if row is None or row.ledger_id != ledger_id:
        raise SyntheticWriteAdmissionDenied('Pinned synthetic ledger identity unavailable')


def _admit(invocation_id, intent, *, ledger_id, experiment_enabled):
    _enabled(experiment_enabled)
    if type(ledger_id) is not str:
        raise SyntheticWriteAdmissionDenied('Synthetic ledger identity unavailable')
    try:
        ledger_id = str(UUID(ledger_id))
    except (ValueError, TypeError, AttributeError):
        raise SyntheticWriteAdmissionDenied('Synthetic ledger identity unavailable') from None
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, invocation_id)
        prior = db.get(SyntheticWriteAdmission, invocation_id)
        if prior is not None:
            raise SyntheticWriteAdmissionUnknown('Synthetic write admission consumed; no reexecution')
        reason = _authority(db, invocation, source, root, approval)
        if reason:
            raise SyntheticWriteAdmissionDenied('Synthetic write authority unavailable: '+reason)
        digest, content = _bound_intent(db, intent, invocation, source, approval,
                                         ledger_id=ledger_id)
        _lock_ledger_identity(db, ledger_id)
        collision = db.scalar(select(SyntheticWriteAdmission).where(
            SyntheticWriteAdmission.ledger_id == ledger_id,
            SyntheticWriteAdmission.record_id == str(intent.record_id),
            SyntheticWriteAdmission.expected_revision == intent.expected_revision)
            .with_for_update())
        if collision is not None:
            raise SyntheticWriteAdmissionUnknown('Synthetic target revision consumed; no reexecution')
        capability = secrets.token_bytes(32)
        db.add(SyntheticWriteAdmission(invocation_id=invocation.id,
            approval_id=approval.id, ledger_id=ledger_id, record_id=str(intent.record_id),
            expected_revision=intent.expected_revision, project_id=invocation.project_id,
            agent_id=source.agent_id, root_id=source.root_id,
            approval_payload_sha256=approval.payload_hash,
            policy_snapshot_sha256=_digest(invocation.policy_snapshot),
            intent_sha256=digest,
            capability_sha256=hashlib.sha256(capability).hexdigest(), status='unknown'))
        db.add(AuditEvent(actor='synthetic-write-admission-fixture',
            action='synthetic.write.admission', resource=invocation.id,
            outcome='unknown', detail={'intent_sha256': digest,
                'ledger_id': ledger_id, 'record_id': str(intent.record_id),
                'expected_revision': intent.expected_revision}))
        try:
            db.commit()  # consumed fence commits before any ledger open or mutation
        except IntegrityError:
            # Concurrent admissions for another invocation can race on the
            # target-revision uniqueness constraint; the winner consumes it.
            raise SyntheticWriteAdmissionUnknown(
                'Synthetic admission conflict; no execution') from None
    return _Permit(invocation_id, digest, capability), content


def execute_governed_fake_write(invocation_id, intent, *, ledger_directory,
        ledger_id, ledger_key, experiment_enabled=False, after_admission_commit=None,
        before_ledger=None, after_effect_commit=None):
    """Consume DB authority, then mutate only the injected private fake ledger.

    The result/receipt is returned transiently. This fixture does not accept a
    product result or clear admission, including when the ledger is replaced.
    """
    _enabled(experiment_enabled)
    if type(ledger_key) is not bytes or len(ledger_key) != 32:
        raise SyntheticWriteAdmissionDenied('Private synthetic write key unavailable')
    if type(ledger_id) is not UUID:
        raise SyntheticWriteAdmissionDenied('Trusted synthetic ledger identity unavailable')
    if type(intent) is not SyntheticWriteIntent:
        raise SyntheticWriteAdmissionDenied('Exact synthetic write intent required')
    permit, content = _admit(invocation_id, intent, ledger_id=str(ledger_id),
                             experiment_enabled=experiment_enabled)
    if after_admission_commit:
        after_admission_commit()
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, invocation_id)
        row = db.scalar(select(SyntheticWriteAdmission).where(
            SyntheticWriteAdmission.invocation_id == invocation_id)
            .with_for_update().execution_options(populate_existing=True))
        if (row is None or approval is None or row.intent_sha256 != permit.intent_sha256 or
                not hmac.compare_digest(row.capability_sha256,
                    hashlib.sha256(permit.capability).hexdigest()) or
                row.ledger_id != str(ledger_id) or
                row.record_id != str(intent.record_id) or
                row.expected_revision != intent.expected_revision or
                row.approval_id != (approval.id if approval else None) or
                row.project_id != invocation.project_id or row.agent_id != source.agent_id or
                row.root_id != source.root_id or
                row.approval_payload_sha256 != approval.payload_hash or
                row.policy_snapshot_sha256 != _digest(invocation.policy_snapshot)):
            raise SyntheticWriteAdmissionDenied('Synthetic write admission binding unavailable')
        reason = _authority(db, invocation, source, root, approval)
        if reason:
            raise SyntheticWriteAdmissionDenied('Synthetic write authority unavailable: '+reason)
        # Hold the current authority locks across the local effect. PostgreSQL
        # fence was already committed in a prior transaction.
        if before_ledger:
            before_ledger()
        ledger = SyntheticWriteLedger(ledger_directory,
            ledger_id=ledger_id, key=ledger_key, experiment_enabled=True)
        receipt = ledger.apply(intent, content, after_effect_commit=after_effect_commit)
        return receipt
