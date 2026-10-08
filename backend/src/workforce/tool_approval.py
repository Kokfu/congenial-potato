"""Exact, durable owner approval for one synthetic tool invocation."""
from datetime import timedelta
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .artifact_read import ArtifactIntegrityError, read_version
from .models import (Approval, ArtifactVersion, AuditEvent, Execution, Task,
                     ToolInvocation, now)
from .tool_policy import evaluate_tool_policy


class ToolApprovalError(ValueError):
    pass


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _target_version(invocation: ToolInvocation) -> str | None:
    if invocation.action == 'project.artifact.write':
        return invocation.arguments.get('expected_parent')
    if invocation.action == 'project.artifact.read':
        return invocation.arguments.get('version_id')
    return None


def exact_payload(invocation: ToolInvocation) -> dict:
    return {'execution_id': invocation.execution_id,
            'project_id': invocation.project_id,
            'action': invocation.action,
            'definition_version': invocation.definition_version,
            'schema_hash': invocation.schema_hash,
            'argument_hash': invocation.argument_hash,
            'arguments': invocation.arguments,
            'resource': invocation.resource,
            'target_version': _target_version(invocation)}


def create_tool_approval(db: Session, invocation: ToolInvocation) -> Approval:
    if invocation.status != 'awaiting_approval':
        raise ToolApprovalError('Invocation does not require approval')
    payload = exact_payload(invocation)
    approval = Approval(execution_id=invocation.execution_id,
                        tool_invocation_id=invocation.id,
                        invocation_key=f'tool:{invocation.id}',
                        payload_hash=_digest(payload), payload=payload,
                        schema_hash=invocation.schema_hash,
                        resource=invocation.resource,
                        target_version=payload['target_version'],
                        status='pending', expires_at=now() + timedelta(days=1))
    db.add(approval)
    db.flush()
    db.add(AuditEvent(actor='worker', action='tool.approval.create',
                      resource=invocation.id, outcome='pending',
                      detail={'approval_id': approval.id,
                              'payload_hash': approval.payload_hash}))
    return approval


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
    invocation = db.execute(select(ToolInvocation).where(ToolInvocation.id == invocation_id)
                            .with_for_update().execution_options(populate_existing=True)).scalar_one()
    approval = db.execute(select(Approval).where(Approval.tool_invocation_id == invocation.id)
                          .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if approval is None:
        raise ToolApprovalError('Approval unavailable')
    if expected_hash != approval.payload_hash:
        raise ToolApprovalError('Approval hash mismatch')
    if approval.status == 'approved' and invocation.status == 'admitted' and approved:
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
        return invocation, approval, None
    reason = _invalid_reason(db, invocation, approval, source)
    if reason is not None:
        approval.status = 'expired' if reason == 'expired' else 'invalidated'
        invocation.status = 'invalidated'
        db.add(AuditEvent(actor=owner_id, action='tool.approval', resource=invocation.id,
                          outcome=approval.status,
                          detail={'approval_id': approval.id, 'reason': reason}))
        return invocation, approval, reason
    approval.status = 'approved'
    approval.decision_payload_hash = approval.payload_hash
    invocation.status = 'admitted'
    db.add(AuditEvent(actor=owner_id, action='tool.approval', resource=invocation.id,
                      outcome='approved', detail={'approval_id': approval.id,
                                                  'payload_hash': approval.payload_hash}))
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
    return invocation_invalid_reason(db, invocation, source,
                                     expected_policy='require_approval')


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
    if decision.effect != expected_policy or decision.snapshot != invocation.policy_snapshot:
        return 'policy_changed'
    if not _precondition_current(db, invocation):
        return 'target_changed'
    return None
