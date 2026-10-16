"""Fixture-only durable metadata acceptance, never a product execution route.

Exact duplicates are historical metadata, not fresh permission. Lost or rejected
results never authorize another job. No text/context or external truth is promoted.
"""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac

from sqlalchemy import select

from .activity import record_activity
from .db import session_factory
from .models import AuditEvent, Project, ProjectActivityCursor, RunnerAttempt, RunnerResult, now
from .reviewed_runner_contract import RunnerContractError
from .runner_admission import RunnerAdmission, _enabled, _locked, _ongoing_reason
from .runner_result_contract import pinned_runner_result, verify_runner_result
from .tool_approval import _digest


class RunnerResultDenied(RunnerContractError):
    pass


@dataclass(frozen=True)
class AcceptedRunnerResult:
    invocation_id: str
    project_id: str
    agent_id: str
    root_id: str
    payload_hash: str
    image_id: str
    manifest_sha256: str
    profile_sha256: str
    job_sha256: str
    input_sha256: str
    input_size: int
    completed_at: datetime
    accepted_at: datetime
    trust_origin: str = 'synthetic_runner'


def _view(row, payload):
    receipt = payload.receipt
    return AcceptedRunnerResult(row.invocation_id, row.project_id, row.agent_id,
        row.root_id, row.payload_hash, payload.image_id, receipt.manifest_sha256,
        receipt.profile_sha256, receipt.job_sha256, receipt.input_sha256,
        receipt.input_size, payload.completed_at, row.accepted_at)


def _event(db, invocation, outcome, reason=None):
    db.add(AuditEvent(actor='runner-result-fixture', action='runner.result',
        resource=invocation.id, outcome=outcome, detail={'reason': reason} if reason else {}))
    record_activity(db, project_id=invocation.project_id, actor='runner-result-fixture',
        action='runner.result', resource=invocation.id, outcome=outcome)


def _deny(db, invocation, approval, attempt, reason):
    invocation.status = 'invalidated'
    if approval is not None and approval.status == 'approved':
        approval.status = 'invalidated'
    attempt.reason = reason  # preserve unknown: execution may have happened
    _event(db, invocation, 'denied', reason)
    db.commit()
    raise RunnerResultDenied('Runner result authority unavailable')


def accept_runner_result(admission: RunnerAdmission, envelope: str, *, key: bytes,
                         experiment_enabled=False, after_commit=None) -> AcceptedRunnerResult:
    _enabled(experiment_enabled)
    if (type(admission) is not RunnerAdmission or type(admission.capability) is not bytes
            or len(admission.capability) != 32):
        raise RunnerResultDenied('Runner capability unavailable')
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, admission.invocation_id)
        # Grant writers lock Project before their grant row. Take the FK lock
        # before grant checks so result/activity inserts cannot invert that order.
        db.scalar(select(Project).where(Project.id == invocation.project_id)
            .with_for_update(read=True, key_share=True))
        attempt = db.scalar(select(RunnerAttempt).where(
            RunnerAttempt.invocation_id == admission.invocation_id).with_for_update()
            .execution_options(populate_existing=True))
        if (attempt is None or not hmac.compare_digest(attempt.capability_hash,
                hashlib.sha256(admission.capability).hexdigest()) or
                attempt.image_id != admission.image_id or attempt.job_sha256 != admission.job_sha256 or
                attempt.manifest_sha256 != admission.manifest_sha256):
            raise RunnerResultDenied('Runner admission binding unavailable')
        # Bad authentication cannot burn legitimate ongoing authority. This
        # historical identity check grants no time or database permission.
        payload = pinned_runner_result(envelope, admission, key=key)
        document = payload.model_dump(mode='json')
        payload_hash = _digest(document)
        row = db.get(RunnerResult, invocation.id)
        if row is not None:
            if (attempt.status != 'accepted' or attempt.reason is not None or
                    invocation.status != 'runner_result_accepted' or
                    attempt.accepted_result_hash != row.payload_hash or
                    row.payload_hash != payload_hash or row.payload_hash != _digest(row.payload) or
                    row.payload != document or row.project_id != invocation.project_id or
                    row.agent_id != attempt.agent_id or row.root_id != attempt.root_id or
                    str(payload.scope.project_id) != row.project_id or
                    str(payload.scope.agent_id) != row.agent_id or str(payload.scope.root_id) != row.root_id or
                    row.trust_origin != 'synthetic_runner'):
                raise RunnerResultDenied('Recorded runner result identity unavailable')
            return _view(row, payload)  # no new acceptance, audit or execution
        reason, manifest = _ongoing_reason(db, invocation, source, root, approval, attempt, admission)
        if reason:
            _deny(db, invocation, approval, attempt, reason)
        # Wait for activity's independent cursor before the final time check;
        # do not stage any accepted event until that check passes.
        db.scalar(select(ProjectActivityCursor).where(
            ProjectActivityCursor.project_id == invocation.project_id)
            .with_for_update().execution_options(populate_existing=True))
        reason, manifest = _ongoing_reason(db, invocation, source, root, approval, attempt, admission)
        if reason:
            _deny(db, invocation, approval, attempt, reason)
        try:
            verify_runner_result(envelope, admission, key=key)
            manifest.current()
        except RunnerContractError:
            _deny(db, invocation, approval, attempt, 'result_not_current')
        row = RunnerResult(invocation_id=invocation.id, project_id=invocation.project_id,
            agent_id=source.agent_id, root_id=source.root_id, payload_hash=payload_hash,
            payload=document, trust_origin='synthetic_runner', accepted_at=now())
        db.add(row)
        attempt.status = 'accepted'
        attempt.accepted_result_hash = payload_hash
        invocation.status = 'runner_result_accepted'
        _event(db, invocation, 'accepted')
        db.commit()
        result = _view(row, payload)
    if after_commit:
        after_commit()
    return result
