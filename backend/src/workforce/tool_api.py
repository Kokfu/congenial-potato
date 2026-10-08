"""Private visibility into proposed fixture tool invocations."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .models import Approval, OwnerSession, Project, ToolInvocation
from .security import current_session, require_csrf
from .tool_approval import ToolApprovalError, review_tool

router = APIRouter()


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approved: bool
    payload_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


@router.post('/api/tool-invocations/{invocation_id}/decision')
def decide_tool(invocation_id: str, data: DecisionInput,
                session: OwnerSession = Depends(require_csrf),
                db: Session = Depends(db_session)):
    try:
        invocation, approval, reason = review_tool(
            db, invocation_id=invocation_id,
            expected_hash=data.payload_hash,
            approved=data.approved, owner_id=session.owner_id)
    except ToolApprovalError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    if reason:
        raise HTTPException(409, f'Approval invalidated: {reason}')
    return {'id': invocation.id, 'status': invocation.status,
            'approval_id': approval.id, 'approval_status': approval.status}


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
    result = []
    for row in rows:
        approval = db.scalar(select(Approval).where(Approval.tool_invocation_id == row.id))
        result.append({'id': row.id, 'execution_id': row.execution_id,
                       'action': row.action, 'definition_version': row.definition_version,
                       'schema_hash': row.schema_hash, 'argument_hash': row.argument_hash,
                       'arguments': row.arguments, 'resource': row.resource,
                       'effect': row.effect, 'policy_decision': row.policy_decision,
                       'policy_snapshot': row.policy_snapshot, 'status': row.status,
                       'approval': ({'id': approval.id, 'status': approval.status,
                                     'payload_hash': approval.payload_hash,
                                     'expires_at': approval.expires_at,
                                     'target_version': approval.target_version}
                                    if approval else None),
                       'created_at': row.created_at})
    return result
