"""Owner commands and reads for prerequisite edges."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .models import AuditEvent, OwnerSession, Task, TaskDependency
from .security import current_session, require_csrf
from .task_graph import TaskGraphError, add_dependency

router = APIRouter()


class DependencyInput(BaseModel):
    prerequisite_task_id: str


@router.get('/api/tasks/{task_id}/dependencies')
def list_task_dependencies(task_id: str, _: OwnerSession = Depends(current_session),
                           db: Session = Depends(db_session)):
    if db.get(Task, task_id) is None:
        raise HTTPException(404, 'Task not found')
    rows = db.scalars(select(TaskDependency).where(
        TaskDependency.dependent_id == task_id).order_by(TaskDependency.created_at,
                                                          TaskDependency.id)).all()
    return [{'id': row.id, 'prerequisite_task_id': row.prerequisite_id} for row in rows]


@router.post('/api/tasks/{task_id}/dependencies', status_code=201)
def create_task_dependency(task_id: str, data: DependencyInput, response: Response,
                           session: OwnerSession = Depends(require_csrf),
                           db: Session = Depends(db_session)):
    try:
        edge, created = add_dependency(db, task_id, data.prerequisite_task_id)
    except TaskGraphError as exc:
        if exc.code in ('task_missing', 'prerequisite_missing'):
            raise HTTPException(404, 'Task not found') from exc
        raise HTTPException(409, 'Task dependency is invalid or cyclic') from exc
    if created:
        db.add(AuditEvent(actor=session.owner_id, action='task.dependency.add',
                          resource=task_id, outcome='allowed',
                          detail={'prerequisite_task_id': data.prerequisite_task_id}))
    else:
        response.status_code = 200
    db.commit()
    return {'id': edge.id, 'task_id': task_id, 'prerequisite_task_id': edge.prerequisite_id}
