"""Separate worker; never run agent work in an HTTP request."""
import time
from decimal import Decimal
from dbos import DBOS, SetWorkflowID
from sqlalchemy import select
from .config import get_settings
from .db import session_factory
from .models import AgentConfigVersion, AuditEvent, BudgetAccount, BudgetReservation, Execution, ModelCall, Outbox, Task, now
from .services import AccessDenied, authorize_agent_project, reserve_budget

RESERVATION = Decimal('0.010000')


def release_reservation(db, execution: Execution) -> None:
    reservation = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == f'model:{execution.id}'))
    if reservation and reservation.status == 'reserved':
        account = db.execute(select(BudgetAccount).where(BudgetAccount.root_id == execution.root_id).with_for_update()).scalar_one()
        account.reserved -= reservation.amount
        reservation.status = 'released'


@DBOS.step()
def fake_model_step(execution_id: str) -> str:
    return f'Synthetic result for execution {execution_id}'


@DBOS.step()
def complete_step(execution_id: str, result: str) -> str:
    with session_factory()() as db:
        execution = db.execute(select(Execution).where(Execution.id == execution_id).with_for_update()).scalar_one()
        task = db.get(Task, execution.task_id)
        if execution.cancelled:
            release_reservation(db, execution)
            execution.status = 'cancelled'
            task.status = 'cancelled'
            db.commit()
            return 'cancelled'
        try:
            authorize_agent_project(db, execution.agent_id, task.project_id, 'project.execute')
        except AccessDenied:
            release_reservation(db, execution)
            execution.status = 'failed'
            task.status = 'failed'
            db.add(AuditEvent(actor=execution.agent_id, action='fixture.complete', resource=task.id, outcome='denied', effect_key=f'fixture:{execution_id}'))
            db.commit()
            return 'denied'
        if execution.status == 'succeeded':
            return 'succeeded'
        config = db.get(AgentConfigVersion, execution.config_version_id)
        if db.scalar(select(ModelCall.id).where(ModelCall.execution_id == execution_id)) is None:
            db.add(ModelCall(execution_id=execution_id, provider='fixture', model_id=config.model_id, result=result))
        release_reservation(db, execution)
        task.status = 'review'
        execution.status = 'succeeded'
        if db.scalar(select(AuditEvent.id).where(AuditEvent.effect_key == f'fixture:{execution_id}')) is None:
            db.add(AuditEvent(actor=execution.agent_id, action='fixture.complete', resource=task.id, outcome='allowed', effect_key=f'fixture:{execution_id}'))
        db.commit()
        return 'succeeded'


@DBOS.workflow()
def run_fixture(execution_id: str) -> str:
    with session_factory()() as db:
        execution = db.execute(select(Execution).where(Execution.id == execution_id).with_for_update()).scalar_one()
        task = db.get(Task, execution.task_id)
        if execution.cancelled:
            execution.status = 'cancelled'
            task.status = 'cancelled'
            db.commit()
            return 'cancelled'
        try:
            authorize_agent_project(db, execution.agent_id, task.project_id, 'project.execute')
            reserve_budget(db, execution.root_id, f'model:{execution_id}', RESERVATION)
        except AccessDenied:
            execution.status = 'failed'
            task.status = 'failed'
            db.add(AuditEvent(actor=execution.agent_id, action='fixture.admit', resource=task.id, outcome='denied', effect_key=f'admit:{execution_id}'))
            db.commit()
            return 'denied'
        execution.status = 'running'
        task.status = 'running'
        db.commit()
    result = fake_model_step(execution_id)
    return complete_step(execution_id, result)


def dispatch_once() -> int:
    dispatched = 0
    with session_factory()() as db:
        rows = db.scalars(select(Outbox).where(Outbox.kind == 'execution.dispatch', Outbox.delivered_at.is_(None)).order_by(Outbox.created_at).with_for_update(skip_locked=True).limit(20)).all()
        for row in rows:
            execution_id = row.payload['execution_id']
            with SetWorkflowID(row.idempotency_key):
                DBOS.start_workflow(run_fixture, execution_id)
            row.delivered_at = now()
            dispatched += 1
        db.commit()
    return dispatched


def main() -> None:
    settings = get_settings()
    DBOS(config={'name': 'workforce', 'system_database_url': settings.workflow_url, 'application_version': 'foundation-v1', 'run_migrations': False, 'log_level': 'WARNING'})
    DBOS.launch()
    try:
        while True:
            dispatch_once()
            time.sleep(0.5)
    finally:
        DBOS.destroy()


if __name__ == '__main__':
    main()
