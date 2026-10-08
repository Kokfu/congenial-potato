"""Cancel one execution subtree under its root admission lock."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Approval, AuditEvent, CollaborationProposal, Execution, MemoryRecord, Task, ToolInvocation


class CancellationError(ValueError):
    pass


def cancel_subtree(db: Session, execution_id: str, actor: str) -> tuple[Execution, int]:
    hint = db.get(Execution, execution_id)
    if hint is None:
        raise CancellationError('execution_missing')
    # Delegation takes this lock before creating any child, so a child cannot
    # appear between the descendant snapshot and cancellation commit.
    root = db.execute(select(Execution).where(Execution.id == hint.root_id)
                      .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if root is None:
        # Older synthetic fixtures may have no persisted root row. They still
        # need a safe cancellation path; delegation rejects such a root.
        root = db.execute(select(Execution).where(Execution.id == hint.id)
                          .with_for_update().execution_options(populate_existing=True)).scalar_one()
    rows = db.scalars(select(Execution).where(Execution.root_id == hint.root_id)
                      .order_by(Execution.id)).all()
    descendants = {execution_id}
    while True:
        additions = {row.id for row in rows if row.parent_id in descendants}
        if additions <= descendants:
            break
        descendants |= additions
    selected = db.scalars(select(Execution).where(Execution.id.in_(descendants))
                          .order_by(Execution.id).with_for_update()
                          .execution_options(populate_existing=True)).all()
    changed = 0
    for row in selected:
        if row.cancelled:
            continue
        row.cancelled = True
        if row.status not in ('succeeded', 'failed', 'cancelled'):
            row.status = 'cancelled'
        task = db.get(Task, row.task_id)
        if task.status != 'completed':
            task.status = 'cancelled'
            task.revision += 1
        db.add(AuditEvent(actor=actor, action='execution.cancel', resource=row.id,
                          outcome='allowed', detail={'subtree_root_id': execution_id}))
        changed += 1
    # Do not wait behind an approval being applied: its effect check re-reads
    # execution.cancelled before writing. The worker sweeps any skipped row.
    approvals = db.scalars(select(Approval).where(
        Approval.execution_id.in_(descendants),
        Approval.status.in_(['pending', 'approved']))
        .with_for_update(skip_locked=True)).all()
    for approval in approvals:
        approval.status = 'invalidated'
        db.add(AuditEvent(actor=actor, action='artifact.approval',
                          resource=approval.resource, outcome='invalidated',
                          detail={'execution_id': approval.execution_id,
                                  'reason': 'execution_cancelled'}))
    proposals = db.scalars(select(CollaborationProposal).where(
        CollaborationProposal.source_execution_id.in_(descendants),
        CollaborationProposal.status == 'pending')
        .with_for_update(skip_locked=True)).all()
    for proposal in proposals:
        proposal.status = 'invalidated'
        db.add(AuditEvent(actor=actor, action='collaboration.decision',
                          resource=proposal.id, outcome='invalidated',
                          detail={'reason': 'execution_cancelled'}))
    memory_candidates = db.scalars(select(MemoryRecord).where(
        MemoryRecord.source_execution_id.in_(descendants),
        MemoryRecord.status == 'candidate').with_for_update()).all()
    for candidate in memory_candidates:
        candidate.status = 'invalidated'
        db.add(AuditEvent(actor=actor, action='memory.review', resource=candidate.id,
                          outcome='invalidated', detail={'reason': 'execution_cancelled'}))
    tools = db.scalars(select(ToolInvocation).where(
        ToolInvocation.execution_id.in_(descendants),
        ToolInvocation.status == 'proposed').with_for_update()).all()
    for invocation in tools:
        invocation.status = 'invalidated'
        db.add(AuditEvent(actor=actor, action='tool.propose', resource=invocation.id,
                          outcome='invalidated', detail={'reason': 'execution_cancelled'}))
    return db.get(Execution, execution_id), changed


def invalidate_cancelled_approvals(db: Session) -> int:
    rows = db.scalars(select(Approval).join(Execution,
        Approval.execution_id == Execution.id).where(
        Execution.cancelled.is_(True), Approval.status.in_(['pending', 'approved']))
        .with_for_update(of=Approval, skip_locked=True).limit(20)).all()
    for approval in rows:
        approval.status = 'invalidated'
        db.add(AuditEvent(actor='worker', action='artifact.approval',
                          resource=approval.resource, outcome='invalidated',
                          detail={'execution_id': approval.execution_id,
                                  'reason': 'execution_cancelled'}))
    return len(rows)


def invalidate_cancelled_collaboration(db: Session) -> int:
    rows = db.scalars(select(CollaborationProposal).join(Execution,
        CollaborationProposal.source_execution_id == Execution.id).where(
        Execution.cancelled.is_(True), CollaborationProposal.status == 'pending')
        .with_for_update(of=CollaborationProposal, skip_locked=True).limit(20)).all()
    for proposal in rows:
        proposal.status = 'invalidated'
        db.add(AuditEvent(actor='worker', action='collaboration.decision',
                          resource=proposal.id, outcome='invalidated',
                          detail={'reason': 'execution_cancelled'}))
    return len(rows)
