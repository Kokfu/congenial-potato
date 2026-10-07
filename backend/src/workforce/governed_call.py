"""Opt-in synthetic priced generation with a durable pre-call cost hold.

The registry intentionally contains only fixtures. A committed ``calling`` hold
is an uncertain outcome after a crash; replay must never issue the call again.
"""
from datetime import datetime, timezone

from sqlalchemy import select

from .budgets import PriceEnvelope, reserve_shared_cost, settle_shared_cost
from .config import get_settings
from .db import session_factory
from .models import AgentConfigVersion, AuditEvent, BudgetReservation, Execution, ModelCall, Task
from .providers import GenerationRequest, GenerationResponse, ProviderError, ProviderErrorKind, registry
from .services import AccessDenied, authorize_agent_project


def price_for(config: AgentConfigVersion) -> PriceEnvelope | None:
    raw = (config.config or {}).get('price_envelope')
    if raw is None:
        return None
    price = PriceEnvelope.model_validate(raw)
    if (price.provider_connection != config.provider_connection or
            price.model_id != config.model_id):
        raise AccessDenied('Price envelope does not match pinned agent configuration')
    return price


def governed_generate(execution_id: str, request: GenerationRequest, price: PriceEnvelope) -> dict:
    settings = get_settings()
    if settings.daily_cap_usd is None:
        raise AccessDenied('Daily cap is not configured')
    key = f'priced-model:{execution_id}'
    # Validate capability and conservative token bounds before acquiring money.
    with session_factory()() as db:
        execution = db.get(Execution, execution_id)
        config = db.get(AgentConfigVersion, execution.config_version_id)
        if config.provider_connection != price.provider_connection or request.model_id != price.model_id:
            raise AccessDenied('Price envelope does not match model request')
        adapter = registry.get(config.provider_connection)
        estimate = adapter.estimate_usage(request)
        if (estimate.input_tokens > price.max_input_tokens or
                request.max_output_tokens > price.max_output_tokens):
            raise AccessDenied('Token bound exceeds price envelope')
        upper = price.upper_bound()

    with session_factory()() as db:
        execution = db.execute(select(Execution).where(Execution.id == execution_id).with_for_update()).scalar_one()
        task = db.get(Task, execution.task_id)
        if execution.cancelled:
            return {'error': 'cancelled', 'retryable': False}
        authorize_agent_project(db, execution.agent_id, task.project_id, 'project.execute')
        prior = db.scalar(select(ModelCall).where(ModelCall.execution_id == execution_id))
        if prior is not None:
            return GenerationResponse(content=prior.result, actual_model=prior.model_id,
                                      provider_request_id=prior.provider_request_id,
                                      finish_reason='recovered', usage=prior.usage).model_dump(mode='json')
        hold = db.scalar(select(BudgetReservation).where(BudgetReservation.invocation_key == key))
        if hold is not None and hold.status in ('calling', 'unknown', 'settled', 'settled_overrun'):
            if hold.status == 'calling':
                hold.status = 'unknown'
                db.commit()
            return {'error': 'outcome_unknown', 'retryable': False}
        hold = reserve_shared_cost(db, execution.root_id, datetime.now(timezone.utc).date(),
                                   key, upper, settings.daily_cap_usd)
        hold.status = 'calling'
        db.add(AuditEvent(actor=execution.agent_id, action='model.call', resource=execution.id,
                          outcome='started', effect_key=f'model-start:{execution_id}'))
        db.commit()

    try:
        with session_factory()() as db:
            execution = db.get(Execution, execution_id)
            if execution.cancelled:
                settle_shared_cost(db, key, 0)
                db.commit()
                return {'error': 'cancelled', 'retryable': False}
        response = adapter.generate(request)
    except ProviderError as exc:
        with session_factory()() as db:
            uncertain = exc.kind in (ProviderErrorKind.TIMEOUT, ProviderErrorKind.TRANSIENT,
                                      ProviderErrorKind.RATE_LIMIT)
            settle_shared_cost(db, key, None if uncertain else 0)
            db.commit()
        return {'error': 'outcome_unknown' if uncertain else exc.kind.value, 'retryable': False}

    actual = price.actual_cost(response.usage.input_tokens, response.usage.output_tokens)
    if response.actual_model != request.model_id:
        with session_factory()() as db:
            settle_shared_cost(db, key, None)
            db.commit()
        return {'error': 'outcome_unknown', 'retryable': False}
    with session_factory()() as db:
        # The call and settlement are separate from the pre-call commit. If this
        # transaction fails, replay observes ``calling`` and retains the hold.
        settle_shared_cost(db, key, actual)
        db.add(ModelCall(execution_id=execution_id, provider=price.provider_connection,
                         model_id=response.actual_model, provider_request_id=response.provider_request_id,
                         usage=response.usage.model_dump(mode='json'), result=response.content))
        execution = db.get(Execution, execution_id)
        db.add(AuditEvent(actor=execution.agent_id, action='model.call', resource=execution_id,
                          outcome='usage_unknown' if actual is None else 'settled',
                          effect_key=f'model-result:{execution_id}'))
        db.commit()
    return response.model_dump(mode='json')
