"""Owner API for catalog inspection and immutable agent configuration revisions."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .budgets import PriceEnvelope
from .config import get_settings
from .models import Agent, AgentConfigVersion, AuditEvent, Execution, ModelCall, OwnerSession
from . import providers
from .providers import ProviderError
from .security import current_session, require_csrf
from .services import AccessDenied

router = APIRouter()


@router.get('/api/executions/{execution_id}/model-call')
def get_model_call(execution_id: str, _: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    if db.get(Execution, execution_id) is None:
        raise HTTPException(404, 'Execution not found')
    row = db.scalar(select(ModelCall).where(ModelCall.execution_id == execution_id))
    if row is None:
        raise HTTPException(404, 'Model call not recorded')
    return {'provider_connection': row.provider, 'model_id': row.model_id,
            'provider_request_id': row.provider_request_id, 'usage': row.usage}


class ConfigUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    instructions: str = Field(min_length=1, max_length=20000)
    provider_connection: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=160)
    price_envelope: PriceEnvelope | None = None
    output_contract: Literal['text', 'collaboration.v1'] = 'text'


@router.get('/api/provider-connections')
def list_provider_connections(refresh: bool = False, _: OwnerSession = Depends(current_session)):
    return [providers.registry.get(connection).discover_models(refresh=refresh).model_dump(mode='json')
            for connection in providers.registry.connections()]


@router.get('/api/agents/{agent_id}/config')
def get_agent_config(agent_id: str, _: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    if db.get(Agent, agent_id) is None:
        raise HTTPException(404, 'Agent not found')
    rows = db.scalars(select(AgentConfigVersion).where(AgentConfigVersion.agent_id == agent_id)
                      .order_by(AgentConfigVersion.version)).all()
    return {'agent_id': agent_id, 'versions': [
        {'id': row.id, 'version': row.version, 'instructions': row.instructions,
         'provider_connection': row.provider_connection, 'model_id': row.model_id,
         'price_envelope': (row.config or {}).get('price_envelope'),
         'output_contract': (row.config or {}).get('output_contract', 'text'),
         'created_at': row.created_at} for row in rows]}


@router.put('/api/agents/{agent_id}/config')
def update_agent_config(agent_id: str, data: ConfigUpdate, session: OwnerSession = Depends(require_csrf),
                        db: Session = Depends(db_session)):
    agent = db.execute(select(Agent).where(Agent.id == agent_id).with_for_update()).scalar_one_or_none()
    if agent is None:
        raise HTTPException(404, 'Agent not found')
    current = db.scalar(select(AgentConfigVersion).where(AgentConfigVersion.agent_id == agent_id)
                        .order_by(AgentConfigVersion.version.desc()).limit(1))
    if current is None or current.version != data.expected_version:
        raise HTTPException(409, 'Agent config version changed')
    try:
        capabilities = providers.registry.get(data.provider_connection).describe_capabilities(data.model_id)
    except ProviderError as exc:
        raise HTTPException(422, str(exc)) from exc
    if data.output_contract == 'collaboration.v1' and not capabilities.structured_output:
        raise HTTPException(422, 'Selected model lacks validated structured output')
    price = data.price_envelope
    if price is not None:
        if price.provider_connection != data.provider_connection or price.model_id != data.model_id:
            raise HTTPException(422, 'Price envelope must match the selected connection and model')
        if (price.max_input_tokens > capabilities.max_input_tokens or
                price.max_output_tokens > capabilities.max_output_tokens or
                price.max_output_tokens < (512 if data.output_contract == 'collaboration.v1' else 128)):
            raise HTTPException(422, 'Price envelope token bounds do not support the selected model request')
        try:
            upper = price.upper_bound()
        except AccessDenied as exc:
            raise HTTPException(422, 'Price envelope has expired or has no price') from exc
        daily_cap = get_settings().daily_cap_usd
        if daily_cap is None or daily_cap < upper:
            raise HTTPException(422, 'Daily cap is unavailable or below the price upper bound')
    revision = AgentConfigVersion(agent_id=agent.id, version=current.version + 1,
                                  instructions=data.instructions, provider_connection=data.provider_connection,
                                  model_id=data.model_id,
                                  config={**({'price_envelope': price.model_dump(mode='json')} if price else {}),
                                          'output_contract': data.output_contract})
    db.add(revision)
    db.flush()
    db.add(AuditEvent(actor=session.owner_id, action='agent.config.update', resource=agent.id,
                      outcome='allowed', detail={'from_version': current.version, 'to_version': revision.version,
                                                 'provider_connection': revision.provider_connection,
                                                 'model_id': revision.model_id,
                                                 'priced': price is not None}))
    db.commit()
    return {'agent_id': agent.id, 'config_version_id': revision.id, 'version': revision.version}
