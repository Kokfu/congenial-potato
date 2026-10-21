"""Owner commands and reads for prerequisite edges."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import ArtifactVersion, DocumentPlanTask, DocumentDraftRun
from .artifact_read import read_version, ArtifactIntegrityError

from .db import db_session
from .models import Approval, AuditEvent, Execution, OwnerSession, Task, TaskAssignment, TaskDependency
from .security import current_session, require_csrf
from .services import AccessDenied
from .task_assignment import AssignmentError, assign_executor
from .task_graph import TaskGraphError, add_dependency

router = APIRouter()


class AssignmentInput(BaseModel):
    agent_id: str
    expected_revision: int = Field(ge=1)


class AcceptanceInput(BaseModel):
    expected_revision: int = Field(ge=1)


@router.get('/api/tasks/{task_id}/assignments')
def list_task_assignments(task_id: str, _: OwnerSession = Depends(current_session),
                          db: Session = Depends(db_session)):
    if db.get(Task, task_id) is None:
        raise HTTPException(404, 'Task not found')
    rows = db.scalars(select(TaskAssignment).where(TaskAssignment.task_id == task_id)).all()
    return [{'id': row.id, 'agent_id': row.agent_id,
             'assigned_by': row.assigned_by, 'created_at': row.created_at} for row in rows]


@router.post('/api/tasks/{task_id}/assignments', status_code=201)
def create_task_assignment(task_id: str, data: AssignmentInput, response: Response,
                           session: OwnerSession = Depends(require_csrf),
                           db: Session = Depends(db_session)):
    task = db.execute(select(Task).where(Task.id == task_id).with_for_update()).scalar_one_or_none()
    if task is None:
        raise HTTPException(404, 'Task not found')
    if task.revision != data.expected_revision:
        raise HTTPException(409, 'Task revision changed')
    try:
        assignment, created = assign_executor(db, task, data.agent_id, session.owner_id)
    except AccessDenied as exc:
        raise HTTPException(403, 'Project access denied') from exc
    except AssignmentError as exc:
        raise HTTPException(409, str(exc)) from exc
    if created:
        db.add(AuditEvent(actor=session.owner_id, action='task.assign', resource=task.id,
                          outcome='allowed', detail={'agent_id': assignment.agent_id}))
    else:
        response.status_code = 200
    db.commit()
    return {'id': assignment.id, 'task_id': task.id, 'agent_id': assignment.agent_id,
            'revision': task.revision}


@router.post('/api/tasks/{task_id}/accept')
def accept_task(task_id: str, data: AcceptanceInput,
                session: OwnerSession = Depends(require_csrf),
                db: Session = Depends(db_session)):
    task = db.execute(select(Task).where(Task.id == task_id).with_for_update()).scalar_one_or_none()
    if task is None:
        raise HTTPException(404, 'Task not found')
    if task.revision != data.expected_revision or task.status != 'review':
        raise HTTPException(409, 'Task is not ready for acceptance at this revision')
    unresolved = db.scalar(select(Approval.id).join(Execution,
        Approval.execution_id == Execution.id).where(Execution.task_id == task_id,
        Approval.status.in_(['pending', 'approved'])).limit(1))
    if unresolved is not None:
        raise HTTPException(409, 'Task has unresolved artifact approval')
    if db.get(DocumentPlanTask, task_id) is not None:
        version = db.scalar(select(ArtifactVersion).join(Execution,
            ArtifactVersion.execution_id == Execution.id).join(DocumentDraftRun,
            DocumentDraftRun.execution_id == Execution.id).where(Execution.task_id == task_id)
            .order_by(ArtifactVersion.version.desc()).limit(1))
        try:
            if version is None or read_version(db, project_id=task.project_id, version_id=version.id) is None:
                raise ArtifactIntegrityError('Reviewed draft has no verified saved artifact')
        except ArtifactIntegrityError as exc:
            raise HTTPException(409, 'Reviewed draft requires a verified saved artifact') from exc
    task.status = 'completed'
    task.revision += 1
    db.add(AuditEvent(actor=session.owner_id, action='task.accept', resource=task.id,
                      outcome='allowed', detail={'revision': task.revision}))
    db.commit()
    return {'id': task.id, 'status': task.status, 'revision': task.revision}


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
