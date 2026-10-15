"""Owner-authored, revisioned tool resource policy."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .models import OwnerSession, PolicyRule, Project
from .security import current_session, require_csrf
from .tool_policy import PolicyError, set_tool_policy

router = APIRouter()


class RuleInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: UUID
    agent_id: UUID | None = None
    action: Literal['project.memory.search', 'project.artifact.read',
                    'project.artifact.write', 'project.web.read', 'project.runner.digest']
    resource_id: UUID | None = None
    host: str | None = None
    profile_id: Literal['synthetic.text-digest'] | None = None
    effect: Literal['allow', 'deny', 'require_approval']


@router.get('/api/tool-policies')
def list_tool_policies(project_id: UUID,
                       _: OwnerSession = Depends(current_session),
                       db: Session = Depends(db_session)):
    if db.get(Project, str(project_id)) is None:
        raise HTTPException(404, 'Project not found')
    prefix = f'project:{project_id}'
    rows = db.scalars(select(PolicyRule).where(
        (PolicyRule.resource == prefix) | (PolicyRule.resource.startswith(prefix + '/')))
        .order_by(PolicyRule.subject, PolicyRule.action, PolicyRule.resource)
        .limit(200)).all()
    return [{'id': row.id, 'subject': row.subject, 'action': row.action,
             'resource': row.resource, 'effect': row.effect,
             'revision': row.revision} for row in rows]


@router.post('/api/tool-policies', status_code=201)
def upsert_tool_policy(data: RuleInput,
                       session: OwnerSession = Depends(require_csrf),
                       db: Session = Depends(db_session)):
    try:
        if (data.host is not None and data.action != 'project.web.read') or (data.host is not None and data.resource_id is not None) or (data.resource_id is not None and data.action == 'project.web.read'):
            raise PolicyError('Invalid policy resource')
        if ((data.profile_id is not None and data.action != 'project.runner.digest')
                or (data.profile_id is not None and
                    (data.host is not None or data.resource_id is not None))
                or (data.action == 'project.runner.digest' and
                    (data.host is not None or data.resource_id is not None))):
            raise PolicyError('Invalid runner policy resource')
        row = set_tool_policy(db, project_id=str(data.project_id),
                              agent_id=str(data.agent_id) if data.agent_id else None,
                              action=data.action,
                              resource_id=(data.profile_id if data.profile_id is not None else
                                           data.host if data.host is not None else
                                           str(data.resource_id) if data.resource_id else None),
                              effect=data.effect, owner_id=session.owner_id)
    except PolicyError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return {'id': row.id, 'subject': row.subject, 'action': row.action,
            'resource': row.resource, 'effect': row.effect,
            'revision': row.revision}
