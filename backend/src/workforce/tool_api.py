"""Private visibility into proposed fixture tool invocations."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .models import OwnerSession, Project, ToolInvocation
from .security import current_session

router = APIRouter()


@router.get('/api/tool-invocations')
def list_tool_invocations(project_id: str,
                          _: OwnerSession = Depends(current_session),
                          db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(ToolInvocation).where(
        ToolInvocation.project_id == project_id)
        .order_by(ToolInvocation.created_at.desc(), ToolInvocation.id)
        .limit(100)).all()
    return [{'id': row.id, 'execution_id': row.execution_id,
             'action': row.action, 'definition_version': row.definition_version,
             'schema_hash': row.schema_hash, 'argument_hash': row.argument_hash,
             'arguments': row.arguments, 'resource': row.resource,
             'effect': row.effect, 'policy_decision': row.policy_decision,
             'policy_snapshot': row.policy_snapshot, 'status': row.status,
             'created_at': row.created_at} for row in rows]
