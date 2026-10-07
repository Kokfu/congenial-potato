"""Owner command for bounded synthetic delegation."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .delegation import DelegationError, DelegationInput, delegate
from .models import Execution, OwnerSession
from .security import current_session, require_csrf
from .services import AccessDenied

router = APIRouter()


@router.get('/api/executions/{execution_id}/children')
def list_children(execution_id: str, _: OwnerSession = Depends(current_session),
                  db: Session = Depends(db_session)):
    if db.get(Execution, execution_id) is None:
        raise HTTPException(404, 'Execution not found')
    children = db.scalars(select(Execution).where(Execution.parent_id == execution_id)
                          .order_by(Execution.created_at, Execution.id)).all()
    return [{'id': row.id, 'task_id': row.task_id, 'agent_id': row.agent_id,
             'root_id': row.root_id, 'depth': row.depth, 'status': row.status}
            for row in children]


@router.post('/api/executions/{execution_id}/delegate', status_code=202)
def delegate_execution(execution_id: str, data: DelegationInput, response: Response,
                       session: OwnerSession = Depends(require_csrf),
                       db: Session = Depends(db_session)):
    try:
        child, created = delegate(db, execution_id, data, session.owner_id)
    except AccessDenied as exc:
        raise HTTPException(403, 'Project access denied') from exc
    except DelegationError as exc:
        raise HTTPException(404 if exc.code == 'source_missing' else 409, exc.code) from exc
    if not created:
        response.status_code = 200
    db.commit()
    return {'id': child.id, 'task_id': child.task_id, 'root_id': child.root_id,
            'parent_id': child.parent_id, 'depth': child.depth, 'status': child.status}
