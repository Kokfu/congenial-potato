"""Owner API for catalog inspection and immutable agent configuration revisions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .models import Agent, AgentConfigVersion, AuditEvent, Execution, ModelCall, OwnerSession
from .providers import ProviderError, registry
from .security import current_session, require_csrf

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


@router.get('/api/provider-connections')
def list_provider_connections(refresh: bool = False, _: OwnerSession = Depends(current_session)):
    return [registry.get(connection).discover_models(refresh=refresh).model_dump(mode='json')
            for connection in registry.connections()]


@router.get('/api/agents/{agent_id}/config')
def get_agent_config(agent_id: str, _: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    if db.get(Agent, agent_id) is None:
        raise HTTPException(404, 'Agent not found')
    rows = db.scalars(select(AgentConfigVersion).where(AgentConfigVersion.agent_id == agent_id)
                      .order_by(AgentConfigVersion.version)).all()
    return {'agent_id': agent_id, 'versions': [
        {'id': row.id, 'version': row.version, 'instructions': row.instructions,
         'provider_connection': row.provider_connection, 'model_id': row.model_id,
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
        registry.get(data.provider_connection).describe_capabilities(data.model_id)
    except ProviderError as exc:
        raise HTTPException(422, str(exc)) from exc
    revision = AgentConfigVersion(agent_id=agent.id, version=current.version + 1,
                                  instructions=data.instructions, provider_connection=data.provider_connection,
                                  model_id=data.model_id)
    db.add(revision)
    db.flush()
    db.add(AuditEvent(actor=session.owner_id, action='agent.config.update', resource=agent.id,
                      outcome='allowed', detail={'from_version': current.version, 'to_version': revision.version,
                                                 'provider_connection': revision.provider_connection,
                                                 'model_id': revision.model_id}))
    db.commit()
    return {'agent_id': agent.id, 'config_version_id': revision.id, 'version': revision.version}
