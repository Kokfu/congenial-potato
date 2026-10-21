"""Recorded source identity only; this module does not build model context."""
from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .models import Execution, ExecutionBriefSource, OwnerSession, Project, ProjectBriefVersion, Task
from .security import current_session
from .brief_context import BriefContextError, preparation_metadata

router = APIRouter()


class BriefSourceError(ValueError):
    pass


def checked_version(db: Session, project_id: str, revision: int, digest: str | None = None):
    row = db.get(ProjectBriefVersion, (project_id, revision), populate_existing=True)
    if row is None or sha256(row.content.encode('utf-8')).hexdigest() != row.digest:
        raise BriefSourceError('Recorded source brief is unavailable or changed')
    if digest is not None and row.digest != digest:
        raise BriefSourceError('Recorded source brief digest changed')
    return row


def current_version(db: Session, project_id: str, expected_revision: int | None = None):
    # Root dispatch takes this project lock before task/agent locks, matching the
    # graph's project-before-task order and serializing owner edits with capture.
    project = db.scalar(select(Project).where(Project.id == project_id).with_for_update()
                        .execution_options(populate_existing=True))
    if project is None:
        raise BriefSourceError('Project not found')
    if expected_revision is not None and expected_revision != project.brief_revision:
        raise BriefSourceError('Brief changed before dispatch; refresh and review it again')
    return checked_version(db, project_id, project.brief_revision)


def attach_source(db: Session, execution: Execution, version: ProjectBriefVersion):
    db.add(ExecutionBriefSource(execution_id=execution.id, project_id=version.project_id,
                               revision=version.revision, digest=version.digest))


def inherit_source(db: Session, parent: Execution, child: Execution):
    source = db.get(ExecutionBriefSource, parent.id)
    # Legacy roots stay explicitly unpinned. Never substitute today's brief.
    if source is None:
        return
    project_id = db.get(Task, child.task_id).project_id
    if source.project_id != project_id:
        raise BriefSourceError('Recorded source brief project mismatch')
    attach_source(db, child, checked_version(db, project_id, source.revision, source.digest))


def source_record(db: Session, execution: Execution) -> dict:
    source = db.get(ExecutionBriefSource, execution.id)
    if source is None:
        return {'status': 'unpinned'}
    if source.project_id != db.get(Task, execution.task_id).project_id:
        raise BriefSourceError('Recorded source brief project mismatch')
    version = checked_version(db, source.project_id, source.revision, source.digest)
    result = {'status': 'pinned', 'project_id': source.project_id, 'revision': source.revision,
              'digest': source.digest, 'content': version.content}
    try:
        result['context'] = preparation_metadata(db, execution.id, result)
    except BriefContextError as exc:
        raise BriefSourceError(str(exc)) from exc
    return result


@router.get('/api/executions/{execution_id}/brief')
def read_source(execution_id: str, _: OwnerSession = Depends(current_session),
                db: Session = Depends(db_session)):
    execution = db.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(404, 'Execution not found')
    try:
        return source_record(db, execution)
    except BriefSourceError as exc:
        raise HTTPException(409, str(exc)) from exc
