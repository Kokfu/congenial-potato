"""Explicit fixture admission only. No API, launcher, receipt or product dispatch.

A committed row consumes the invocation before a private capability is returned.
Lost delivery/execution stays unknown. Rechecking an ongoing admitted attempt is
not a second launch permit; the trusted test bridge must admit before each run.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import secrets
from uuid import UUID

from sqlalchemy import select

from .activity import record_activity
from .db import session_factory
from .models import Approval, AuditEvent, BudgetAccount, Execution, RunnerAttempt, ToolInvocation, now
from .reviewed_runner_contract import (MAX_MANIFEST_LIFETIME, RunnerContractError,
    RunnerScope, build_runner_manifest, canonical_manifest, manifest_digest,
    parse_runner_input, verify_runner_manifest)
from .runner_grants import current_runner_grant_record
from .tool_approval import _digest, _invalid_reason, exact_payload


class RunnerAdmissionDenied(RunnerContractError):
    pass


class RunnerAdmissionUnknown(RunnerContractError):
    pass


@dataclass(frozen=True)
class RunnerAdmission:
    invocation_id: str
    manifest_raw: str = field(repr=False)
    manifest_sha256: str
    image_id: str
    job_sha256: str
    capability: bytes = field(repr=False)


def _enabled(enabled):
    if enabled is not True:
        raise RunnerAdmissionDenied('Runner admission fixture is disabled')


def _locked(db, invocation_id):
    try:
        if type(invocation_id) is not str or str(UUID(invocation_id)) != invocation_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise RunnerAdmissionDenied('Runner identity unavailable') from None
    hint = db.get(ToolInvocation, invocation_id)
    if hint is None or hint.action != 'project.runner.digest':
        raise RunnerAdmissionDenied('Runner proposal unavailable')
    source = db.get(Execution, hint.execution_id)
    if source is None:
        raise RunnerAdmissionDenied('Runner source unavailable')
    root = db.scalar(select(Execution).where(Execution.id == source.root_id)
        .with_for_update().execution_options(populate_existing=True))
    db.refresh(source)
    invocation = db.scalar(select(ToolInvocation).where(ToolInvocation.id == invocation_id)
        .with_for_update().execution_options(populate_existing=True))
    approval = db.scalar(select(Approval).where(Approval.tool_invocation_id == invocation_id)
        .with_for_update().execution_options(populate_existing=True))
    return invocation, source, root, approval


def _reason(db, invocation, source, root, approval):
    if root is None or root.id != source.root_id or root.cancelled:
        return 'root_unavailable'
    if invocation.status != 'approved_staged' or invocation.effect != 'write':
        return 'invocation_unavailable'
    if (approval is None or approval.status != 'approved' or
            invocation.policy_decision != 'require_approval' or
            approval.decision_payload_hash != approval.payload_hash):
        return 'approval_unavailable'
    reason = _invalid_reason(db, invocation, approval, source)
    if reason:
        return reason
    account = db.scalar(select(BudgetAccount).where(BudgetAccount.root_id == source.root_id)
        .with_for_update().execution_options(populate_existing=True))
    if (account is None or account.currency != 'USD' or account.spent < 0 or
            account.reserved < 0 or account.cap-account.spent-account.reserved <= 0):
        return 'root_budget_unavailable'
    return None


def _binding(invocation):
    return _digest({'approval_payload': exact_payload(invocation),
                    'policy': invocation.policy_snapshot})


def _audit(db, invocation, outcome, reason=None):
    db.add(AuditEvent(actor='runner-admission-fixture', action='runner.admission',
        resource=invocation.id, outcome=outcome, detail={'reason': reason} if reason else {}))
    record_activity(db, project_id=invocation.project_id, actor='runner-admission-fixture',
        action='runner.admission', resource=invocation.id, outcome=outcome)


def _deny(db, invocation, approval, reason, attempt=None):
    invocation.status = 'invalidated'
    if approval is not None and approval.status == 'approved':
        approval.status = 'invalidated'
    if attempt is not None:
        attempt.reason = reason  # preserve unknown; never infer no execution
    _audit(db, invocation, 'denied', reason)
    db.commit()
    raise RunnerAdmissionDenied('Runner authority unavailable')


def admit_runner_attempt(invocation_id: str, *, experiment_enabled=False,
                         after_commit=None) -> RunnerAdmission:
    _enabled(experiment_enabled)
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, invocation_id)
        if db.get(RunnerAttempt, invocation_id) is not None:
            raise RunnerAdmissionUnknown('Runner admission consumed; no repeat')
        reason = _reason(db, invocation, source, root, approval)
        if reason:
            _deny(db, invocation, approval, reason)
        grant = current_runner_grant_record(db, project_id=invocation.project_id,
                                           agent_id=source.agent_id)
        issued = now()
        manifest = build_runner_manifest(
            parse_runner_input(json.dumps(invocation.arguments['input'])),
            scope=RunnerScope(project_id=UUID(invocation.project_id), agent_id=UUID(source.agent_id),
                              root_id=UUID(source.root_id), attempt_id=UUID(invocation.id)),
            issued_at=issued, expires_at=min(issued+MAX_MANIFEST_LIFETIME,
                                            grant.expires_at, approval.expires_at))
        capability = secrets.token_bytes(32)
        admission = RunnerAdmission(invocation.id, canonical_manifest(manifest),
            manifest_digest(manifest), grant.image_id, grant.job_sha256, capability)
        db.add(RunnerAttempt(invocation_id=invocation.id, approval_id=approval.id,
            agent_id=source.agent_id, root_id=source.root_id, binding_hash=_binding(invocation),
            manifest_sha256=admission.manifest_sha256,
            capability_hash=hashlib.sha256(capability).hexdigest(),
            image_id=grant.image_id, job_sha256=grant.job_sha256,
            issued_at=issued, expires_at=manifest.expires_at, status='unknown'))
        _audit(db, invocation, 'unknown')
        db.commit()  # independent fence before private capability/manifest delivery
    if after_commit:
        after_commit()
    try:
        manifest.current()
    except RunnerContractError:
        raise RunnerAdmissionUnknown('Runner delivery expired; no repeat') from None
    return admission


def check_runner_authority(admission: RunnerAdmission, *, experiment_enabled=False) -> bool:
    """Fresh pre-start/post-job checks for an ongoing admission; never launches."""
    _enabled(experiment_enabled)
    if (type(admission) is not RunnerAdmission or type(admission.capability) is not bytes
            or len(admission.capability) != 32):
        raise RunnerAdmissionDenied('Runner capability unavailable')
    with session_factory()() as db:
        invocation, source, root, approval = _locked(db, admission.invocation_id)
        attempt = db.scalar(select(RunnerAttempt).where(
            RunnerAttempt.invocation_id == admission.invocation_id).with_for_update()
            .execution_options(populate_existing=True))
        if (attempt is None or not hmac.compare_digest(attempt.capability_hash,
                hashlib.sha256(admission.capability).hexdigest())):
            raise RunnerAdmissionDenied('Runner capability unavailable')
        if attempt.status == 'accepted':
            raise RunnerAdmissionUnknown('Runner result already accepted; no execution')
        reason, manifest = _ongoing_reason(db, invocation, source, root, approval, attempt, admission)
        if reason:
            _deny(db, invocation, approval, reason, attempt)
        manifest.current()
    return True


def _ongoing_reason(db, invocation, source, root, approval, attempt, admission):
    manifest = None
    reason = _reason(db, invocation, source, root, approval)
    if reason is None and (attempt.status != 'unknown' or attempt.reason is not None or
            attempt.approval_id != approval.id or attempt.agent_id != source.agent_id or
            attempt.root_id != source.root_id or attempt.binding_hash != _binding(invocation) or
            attempt.image_id != admission.image_id or attempt.job_sha256 != admission.job_sha256 or
            attempt.manifest_sha256 != admission.manifest_sha256 or
            attempt.image_id != invocation.policy_snapshot['runner_grant']['image_id'] or
            attempt.job_sha256 != invocation.policy_snapshot['runner_grant']['job_sha256']):
        reason = 'attempt_changed'
    try:
        manifest = verify_runner_manifest(admission.manifest_raw,
                                          expected_sha256=attempt.manifest_sha256)
        if (str(manifest.scope.attempt_id) != invocation.id or
                str(manifest.scope.project_id) != invocation.project_id or
                str(manifest.scope.agent_id) != source.agent_id or
                str(manifest.scope.root_id) != source.root_id or
                manifest.input.model_dump(mode='json') != invocation.arguments['input'] or
                manifest.issued_at != attempt.issued_at or manifest.expires_at != attempt.expires_at):
            reason = 'manifest_changed'
    except RunnerContractError:
        reason = 'manifest_unavailable'
    return reason, manifest
