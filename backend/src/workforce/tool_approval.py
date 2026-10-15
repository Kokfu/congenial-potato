"""Exact, durable owner approval for one synthetic tool invocation."""
from datetime import timedelta
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .artifact_read import ArtifactIntegrityError, read_version
from .models import (Approval, ArtifactVersion, AuditEvent, BudgetAccount, Execution, Task,
                     RunnerProfileGrant, ToolInvocation, now)
from .tool_policy import evaluate_tool_policy
from .activity import record_activity


class ToolApprovalError(ValueError):
    pass


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _target_version(invocation: ToolInvocation) -> str | None:
    if invocation.action in ('project.web.read', 'project.runner.digest'):
        key = 'runner_grant' if invocation.action == 'project.runner.digest' else 'destination_grant'
        grant = invocation.policy_snapshot.get(key, {})
        if grant.get('id') and grant.get('revision'):
            return f"{grant['id']}:{grant['revision']}"
        return None
    if invocation.action == 'project.artifact.write':
        return invocation.arguments.get('expected_parent')
    if invocation.action == 'project.artifact.read':
        return invocation.arguments.get('version_id')
    return None


def exact_payload(invocation: ToolInvocation) -> dict:
    payload = {'execution_id': invocation.execution_id,
            'project_id': invocation.project_id,
            'action': invocation.action,
            'definition_version': invocation.definition_version,
            'schema_hash': invocation.schema_hash,
            'argument_hash': invocation.argument_hash,
            'arguments': invocation.arguments,
            'resource': invocation.resource,
            'target_version': _target_version(invocation)}
    if invocation.action == 'project.runner.digest':
        payload['runner_binding'] = invocation.policy_snapshot.get('runner_grant')
        payload['runner_scope'] = invocation.policy_snapshot.get('runner_scope')
    return payload


def create_tool_approval(db: Session, invocation: ToolInvocation) -> Approval:
    if invocation.status != 'awaiting_approval':
        raise ToolApprovalError('Invocation does not require approval')
    if invocation.action == 'project.runner.digest':
        source = db.get(Execution, invocation.execution_id)
        reason = (invocation_invalid_reason(db, invocation, source, 'require_approval')
                  if source else 'source_unavailable')
        if reason:
            raise ToolApprovalError(reason)
    payload = exact_payload(invocation)
    expiry = now() + timedelta(days=1)
    if invocation.action == 'project.runner.digest':
        grant = db.get(RunnerProfileGrant, invocation.policy_snapshot['runner_grant']['id'])
        expiry = min(expiry, grant.expires_at)
    approval = Approval(execution_id=invocation.execution_id,
                        tool_invocation_id=invocation.id,
                        invocation_key=f'tool:{invocation.id}',
                        payload_hash=_digest(payload), payload=payload,
                        schema_hash=invocation.schema_hash,
                        resource=invocation.resource,
                        target_version=payload['target_version'],
                        status='pending', expires_at=expiry)
    db.add(approval)
    db.flush()
    db.add(AuditEvent(actor='worker', action='tool.approval.create',
                      resource=invocation.id, outcome='pending',
                      detail={'approval_id': approval.id,
                              'payload_hash': approval.payload_hash}))
    record_activity(db, project_id=invocation.project_id, actor='worker',
                    action='tool.approval.create', resource=invocation.id,
                    outcome='pending')
    return approval


def stage_web_read_approval(db: Session, *, invocation_id: str,
                            owner_id: str) -> tuple[ToolInvocation, Approval | None, str | None]:
    """Require an exact approval while keeping outbound execution unavailable."""
    return _stage_inert_approval(db, invocation_id=invocation_id,
                                owner_id=owner_id, action='project.web.read')


def stage_runner_approval(db: Session, *, invocation_id: str,
                           owner_id: str) -> tuple[ToolInvocation, Approval | None, str | None]:
    return _stage_inert_approval(db, invocation_id=invocation_id,
                                owner_id=owner_id, action='project.runner.digest')


def _stage_inert_approval(db: Session, *, invocation_id: str, owner_id: str,
                         action: str) -> tuple[ToolInvocation, Approval | None, str | None]:
    hint = db.get(ToolInvocation, invocation_id)
    if hint is None or hint.action != action:
        raise ToolApprovalError('Staged tool proposal unavailable')
    source = db.get(Execution, hint.execution_id)
    if source is None:
        raise ToolApprovalError('Execution unavailable')
    db.execute(select(Execution).where(Execution.id == source.root_id)
               .with_for_update()).scalar_one_or_none()
    db.refresh(source)
    invocation = db.execute(select(ToolInvocation).where(
        ToolInvocation.id == invocation_id).with_for_update()
        .execution_options(populate_existing=True)).scalar_one()
    if invocation.status == 'awaiting_approval':
        approval = db.scalar(select(Approval).where(
            Approval.tool_invocation_id == invocation.id)
            .with_for_update().execution_options(populate_existing=True))
        if approval is None or approval.status != 'pending':
            raise ToolApprovalError('Approval unavailable')
        if action == 'project.runner.digest':
            reason = _invalid_reason(db, invocation, approval, source)
            if reason:
                approval.status = 'expired' if reason == 'expired' else 'invalidated'
                invocation.status = 'invalidated'
                db.add(AuditEvent(actor=owner_id, action='tool.approval.stage',
                    resource=invocation.id, outcome='invalidated', detail={'reason': reason}))
                record_activity(db, project_id=invocation.project_id, actor=owner_id,
                    action='tool.approval.stage', resource=invocation.id, outcome='invalidated')
                return invocation, approval, reason
        return invocation, approval, None
    if invocation.status != 'proposed':
        raise ToolApprovalError('Staged tool proposal is no longer open')
    reason = invocation_invalid_reason(db, invocation, source,
                                       expected_policy='require_approval')
    if reason is None and db.get(BudgetAccount, source.root_id) is None:
        reason = 'root_budget_unavailable'
    if reason is not None:
        invocation.status = 'invalidated'
        db.add(AuditEvent(actor=owner_id, action='tool.approval.stage',
                          resource=invocation.id, outcome='invalidated',
                          detail={'reason': reason}))
        record_activity(db, project_id=invocation.project_id, actor=owner_id,
                        action='tool.approval.stage', resource=invocation.id,
                        outcome='invalidated')
        return invocation, None, reason
    invocation.status = 'awaiting_approval'
    approval = create_tool_approval(db, invocation)
    db.add(AuditEvent(actor=owner_id, action='tool.approval.stage',
                      resource=invocation.id, outcome='pending',
                      detail={'approval_id': approval.id}))
    return invocation, approval, None


def _precondition_current(db: Session, invocation: ToolInvocation) -> bool:
    if invocation.action == 'project.artifact.write':
        head = db.scalar(select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == invocation.arguments['artifact_id'],
            ArtifactVersion.project_id == invocation.project_id)
            .order_by(ArtifactVersion.version.desc()).limit(1))
        return (head.id if head else None) == invocation.arguments['expected_parent']
    if invocation.action == 'project.artifact.read':
        try:
            return read_version(db, project_id=invocation.project_id,
                                version_id=invocation.arguments['version_id']) is not None
        except ArtifactIntegrityError:
            return False
    return True


def review_tool(db: Session, *, invocation_id: str, expected_hash: str,
                approved: bool, owner_id: str) -> tuple[ToolInvocation, Approval, str | None]:
    hint = db.get(ToolInvocation, invocation_id)
    if hint is None:
        raise ToolApprovalError('Invocation unavailable')
    source = db.get(Execution, hint.execution_id)
    if source is None:
        raise ToolApprovalError('Execution unavailable')
    db.execute(select(Execution).where(Execution.id == source.root_id)
               .with_for_update()).scalar_one_or_none()
    db.refresh(source)
    invocation = db.execute(select(ToolInvocation).where(ToolInvocation.id == invocation_id)
                            .with_for_update().execution_options(populate_existing=True)).scalar_one()
    approval = db.execute(select(Approval).where(Approval.tool_invocation_id == invocation.id)
                          .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if approval is None:
        raise ToolApprovalError('Approval unavailable')
    if expected_hash != approval.payload_hash:
        raise ToolApprovalError('Approval hash mismatch')
    if (approval.status == 'approved' and invocation.status in
            ('admitted', 'approved_staged') and approved):
        return invocation, approval, None
    if approval.status == 'rejected' and invocation.status == 'rejected' and not approved:
        return invocation, approval, None
    if approval.status != 'pending' or invocation.status != 'awaiting_approval':
        raise ToolApprovalError('Approval already decided')
    if not approved:
        approval.status = 'rejected'
        invocation.status = 'rejected'
        db.add(AuditEvent(actor=owner_id, action='tool.approval', resource=invocation.id,
                          outcome='rejected', detail={'approval_id': approval.id}))
        record_activity(db, project_id=invocation.project_id, actor=owner_id,
                        action='tool.approval', resource=invocation.id,
                        outcome='rejected')
        return invocation, approval, None
    reason = _invalid_reason(db, invocation, approval, source)
    if reason is not None:
        approval.status = 'expired' if reason == 'expired' else 'invalidated'
        invocation.status = 'invalidated'
        db.add(AuditEvent(actor=owner_id, action='tool.approval', resource=invocation.id,
                          outcome=approval.status,
                          detail={'approval_id': approval.id, 'reason': reason}))
        record_activity(db, project_id=invocation.project_id, actor=owner_id,
                        action='tool.approval', resource=invocation.id,
                        outcome=approval.status)
        return invocation, approval, reason
    approval.status = 'approved'
    approval.decision_payload_hash = approval.payload_hash
    invocation.status = ('approved_staged' if invocation.action in ('project.web.read', 'project.runner.digest')
                         else 'admitted')
    db.add(AuditEvent(actor=owner_id, action='tool.approval', resource=invocation.id,
                      outcome='approved', detail={'approval_id': approval.id,
                                                  'payload_hash': approval.payload_hash}))
    record_activity(db, project_id=invocation.project_id, actor=owner_id,
                    action='tool.approval', resource=invocation.id,
                    outcome='approved')
    return invocation, approval, None


def _invalid_reason(db: Session, invocation: ToolInvocation,
                    approval: Approval, source: Execution) -> str | None:
    if approval.expires_at <= now():
        return 'expired'
    payload = exact_payload(invocation)
    if (_digest(payload) != approval.payload_hash or approval.payload != payload or
        approval.schema_hash != invocation.schema_hash or
        approval.resource != invocation.resource or
        approval.target_version != payload['target_version'] or
        approval.execution_id != invocation.execution_id):
        return 'approval_payload_changed'
    reason = invocation_invalid_reason(db, invocation, source,
                                       expected_policy='require_approval')
    # Locks/authority checks can consume the remaining approval lifetime.
    return reason or ('expired' if approval.expires_at <= now() else None)


def invocation_invalid_reason(db: Session, invocation: ToolInvocation,
                              source: Execution, expected_policy: str) -> str | None:
    from .tool_gateway import parse_tool_output, ToolProposalError
    task = db.get(Task, source.task_id)
    if source.cancelled or source.status != 'succeeded' or task is None or task.project_id != invocation.project_id:
        return 'source_unavailable'
    try:
        definition, arguments, resource, argument_hash = parse_tool_output(json.dumps({
            'version': invocation.definition_version,
            'action': invocation.action, 'arguments': invocation.arguments}))
    except ToolProposalError:
        return 'schema_or_arguments_changed'
    if (definition.schema_hash != invocation.schema_hash or
        definition.version != invocation.definition_version or
        arguments != invocation.arguments or resource != invocation.resource or
        argument_hash != invocation.argument_hash):
        return 'schema_or_arguments_changed'
    decision = evaluate_tool_policy(db, agent_id=source.agent_id,
                                    project_id=invocation.project_id,
                                    action=invocation.action,
                                    resource=invocation.resource)
    snapshot = decision.snapshot
    if invocation.action == 'project.web.read' and decision.effect != 'deny':
        from .network_policy import canonical_public_url
        from .local_read_experiment import ReadDenied
        from .read_grants import active_read_grant_record
        try:
            host, _ = canonical_public_url(invocation.arguments['url'])
            grant = active_read_grant_record(db, project_id=invocation.project_id,
                agent_id=source.agent_id, host=host)
        except ReadDenied:
            return 'destination_grant_unavailable'
        snapshot = {**snapshot, 'destination_grant': {
            'id': grant.id, 'revision': grant.revision}}
    if invocation.action == 'project.runner.digest' and decision.effect != 'deny':
        from .runner_grants import (RunnerGrantDenied, current_runner_grant_record,
                                    runner_grant_snapshot, runner_scope_snapshot)
        root = db.scalar(select(Execution).where(Execution.id == source.root_id)
            .with_for_update().execution_options(populate_existing=True))
        if root is None or root.cancelled:
            return 'source_unavailable'
        account = db.scalar(select(BudgetAccount).where(BudgetAccount.root_id == source.root_id)
            .with_for_update().execution_options(populate_existing=True))
        if account is None or account.cap - account.spent - account.reserved <= 0:
            return 'root_budget_unavailable'
        try:
            grant = current_runner_grant_record(db, project_id=invocation.project_id,
                                               agent_id=source.agent_id)
        except RunnerGrantDenied:
            return 'runner_grant_unavailable'
        snapshot = {**snapshot, 'runner_grant': runner_grant_snapshot(grant),
                    'runner_scope': runner_scope_snapshot(source)}
    if decision.effect != expected_policy or snapshot != invocation.policy_snapshot:
        return 'policy_changed'
    if not _precondition_current(db, invocation):
        return 'target_changed'
    return None
