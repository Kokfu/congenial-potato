"""Atomically admit due daily occurrences into the existing durable outbox."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import session_factory
from .models import (AgentConfigVersion, AuditEvent, BudgetAccount, Execution,
                     Outbox, Owner, Schedule, ScheduleOccurrence, Task)
from .schedules import latest_due
from .services import AccessDenied, authorize_agent_project
from .task_assignment import AssignmentError, assign_executor


def _admit(db: Session, schedule: Schedule, instant: datetime) -> bool:
    cursor = schedule.last_checked_at or schedule.created_at
    if instant <= cursor:
        return False
    due = latest_due(schedule.id, schedule.timezone, schedule.local_hour,
                     schedule.local_minute,
                     after=cursor,
                     now=instant)
    schedule.last_checked_at = instant
    if due is None:
        return False
    prior = db.scalar(select(ScheduleOccurrence.id).where(
        ScheduleOccurrence.schedule_id == schedule.id,
        ScheduleOccurrence.local_date == due.local_date))
    if prior is not None:
        return False
    occurrence = ScheduleOccurrence(schedule_id=schedule.id,
        project_id=schedule.project_id, local_date=due.local_date,
        scheduled_for=due.scheduled_for, status='skipped')
    db.add(occurrence)
    db.flush()
    active = db.scalar(select(ScheduleOccurrence.id).join(
        Execution, ScheduleOccurrence.execution_id == Execution.id).join(
        Task, Execution.task_id == Task.id).where(
        ScheduleOccurrence.schedule_id == schedule.id,
        ScheduleOccurrence.id != occurrence.id,
        Task.status.in_(['queued', 'running', 'review', 'unknown'])).limit(1))
    reason = 'prior_active' if active else None
    if reason is None:
        try:
            authorize_agent_project(db, schedule.agent_id, schedule.project_id,
                                    'project.execute')
        except AccessDenied:
            reason = 'project_grant_denied'
    config = db.scalar(select(AgentConfigVersion).where(
        AgentConfigVersion.agent_id == schedule.agent_id).order_by(
        AgentConfigVersion.version.desc()).limit(1)) if reason is None else None
    if reason is None and config is None:
        reason = 'agent_config_missing'
    owner_id = db.scalar(select(Owner.id).limit(1))
    if reason is None:
        task = Task(project_id=schedule.project_id, title=schedule.title,
                    work_key=due.key)
        db.add(task)
        db.flush()
        try:
            assign_executor(db, task, schedule.agent_id, owner_id)
        except (AccessDenied, AssignmentError):
            db.delete(task)
            reason = 'agent_unavailable'
    if reason is None:
        execution = Execution(task_id=task.id, agent_id=schedule.agent_id,
                              config_version_id=config.id, root_id='', workflow_id='')
        db.add(execution)
        db.flush()
        execution.root_id = execution.id
        execution.workflow_id = f'execution:{execution.id}'
        db.add(BudgetAccount(root_id=execution.id, cap=Decimal(schedule.root_cap),
                             reserved=Decimal('0'), spent=Decimal('0')))
        db.add(Outbox(kind='execution.dispatch', idempotency_key=execution.workflow_id,
                      payload={'execution_id': execution.id}))
        task.status = 'queued'
        task.revision += 1
        occurrence.status = 'queued'
        occurrence.execution_id = execution.id
    else:
        occurrence.reason = reason
    db.add(AuditEvent(actor='scheduler', action='schedule.occurrence',
                      resource=occurrence.id, outcome=occurrence.status,
                      effect_key=f'schedule:{due.key}',
                      detail={'schedule_id': schedule.id, 'reason': reason,
                              'execution_id': occurrence.execution_id}))
    return reason is None


def schedule_due_once(*, at: datetime) -> int:
    """One tick; row locks and occurrence uniqueness make replay harmless."""
    if at.tzinfo is None:
        raise ValueError('Schedule tick must be timezone-aware')
    instant = at.astimezone(timezone.utc)
    count = 0
    with session_factory()() as db:
        rows = db.scalars(select(Schedule).where(Schedule.enabled.is_(True))
                          .order_by(Schedule.id).with_for_update(skip_locked=True)).all()
        for schedule in rows:
            count += int(_admit(db, schedule, instant))
        db.commit()
    return count
