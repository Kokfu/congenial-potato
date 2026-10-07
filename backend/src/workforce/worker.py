"""Separate worker; never run agent work in an HTTP request."""
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from dbos import DBOS, SetWorkflowID
from sqlalchemy import select
from .config import get_settings
from .db import session_factory
from .models import AgentConfigVersion, AuditEvent, BudgetAccount, BudgetReservation, Execution, ModelCall, Outbox, Task, now
from .services import AccessDenied, authorize_agent_project, reserve_budget
from .artifacts import apply_approved_artifacts, propose_fixture_artifact
from . import providers
from .providers import GenerationRequest, GenerationResponse, ProviderError, TextMessage
from .governed_call import governed_generate, price_for

RESERVATION = Decimal('0.010000')


def release_reservation(db, execution: Execution) -> None:
    reservation = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == f'model:{execution.id}'))
    if reservation and reservation.status == 'reserved':
        account = db.execute(select(BudgetAccount).where(BudgetAccount.root_id == execution.root_id).with_for_update()).scalar_one()
        account.reserved -= reservation.amount
        reservation.status = 'released'


@DBOS.step()
def generate_step(execution_id: str) -> dict:
    with session_factory()() as db:
        execution = db.get(Execution, execution_id)
        config = db.get(AgentConfigVersion, execution.config_version_id)
        task = db.get(Task, execution.task_id)
        if execution.cancelled:
            return {'error': 'cancelled', 'retryable': False}
        try:
            authorize_agent_project(db, execution.agent_id, task.project_id, 'project.execute')
        except AccessDenied:
            return {'error': 'policy_denied', 'retryable': False}
        request = GenerationRequest(request_id=execution_id, model_id=config.model_id,
                                    messages=(TextMessage(role='system', trust_origin='human', text=config.instructions),
                                              TextMessage(role='user', trust_origin='human', text=task.title)),
                                    max_output_tokens=128,
                                    deadline_at=datetime.now(timezone.utc) + timedelta(
                                        seconds=get_settings().model_call_timeout_seconds))
        connection = config.provider_connection
        try:
            price = price_for(config)
        except (AccessDenied, ValueError):
            return {'error': 'policy_denied', 'retryable': False}
    # Release the policy-read transaction before the priced path rechecks and
    # locks the grant; holding both sessions would deadlock on the same row.
    try:
        if price is not None:
            return governed_generate(execution_id, request, price)
        response = providers.registry.get(connection).generate(request)
    except ProviderError as exc:
        return {'error': exc.kind.value, 'retryable': exc.retryable}
    except (AccessDenied, ValueError):
        return {'error': 'policy_denied', 'retryable': False}
    return response.model_dump(mode='json')


@DBOS.step()
def fail_model_step(execution_id: str, error_kind: str, provider_error: str | None = None) -> str:
    with session_factory()() as db:
        execution = db.execute(select(Execution).where(Execution.id == execution_id).with_for_update()).scalar_one()
        task = db.get(Task, execution.task_id)
        release_reservation(db, execution)
        if execution.status in ('failed', 'cancelled', 'unknown'):
            db.commit()
            return execution.status
        execution.status = 'cancelled' if execution.cancelled else ('unknown' if error_kind == 'outcome_unknown' else 'failed')
        task.status = execution.status
        db.add(AuditEvent(actor=execution.agent_id, action='model.generate', resource=execution.id,
                          outcome=error_kind, detail={'provider_error': provider_error} if provider_error else {},
                          effect_key=f'model-error:{execution_id}'))
        db.commit()
        return execution.status


@DBOS.step()
def complete_step(execution_id: str, result: dict) -> str:
    response = GenerationResponse.model_validate(result)
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
            db.add(ModelCall(execution_id=execution_id, provider=config.provider_connection,
                             model_id=response.actual_model, provider_request_id=response.provider_request_id,
                             usage=response.usage.model_dump(mode='json'), result=response.content))
        propose_fixture_artifact(db, execution, response.content)
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
            config = db.get(AgentConfigVersion, execution.config_version_id)
            if price_for(config) is None:
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
    result = generate_step(execution_id)
    if 'error' in result:
        return fail_model_step(execution_id, result['error'], result.get('provider_error'))
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
    DBOS(config={'name': 'workforce', 'system_database_url': settings.workflow_url, 'application_version': 'usage-normalization-v1', 'run_migrations': False, 'log_level': 'WARNING'})
    DBOS.launch()
    try:
        while True:
            dispatch_once()
            apply_approved_artifacts()
            time.sleep(0.5)
    finally:
        DBOS.destroy()


if __name__ == '__main__':
    main()
