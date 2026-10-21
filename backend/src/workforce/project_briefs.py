"""Owner-authored source history; never implicitly added to execution context."""
from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .activity import record_activity
from .db import db_session
from .models import AuditEvent, OwnerSession, Project, ProjectBriefVersion
from .security import current_session, require_csrf

router = APIRouter()


class BriefInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(strict=True, ge=1)
    content: str = Field(strict=True, max_length=20000)


def add_version(db: Session, project: Project, actor: str) -> ProjectBriefVersion:
    row = ProjectBriefVersion(project_id=project.id, revision=project.brief_revision,
        content=project.objective, digest=sha256(project.objective.encode('utf-8')).hexdigest(),
        actor=actor)
    db.add(row)
    return row


def metadata(row: ProjectBriefVersion) -> dict:
    return {'project_id': row.project_id, 'revision': row.revision, 'digest': row.digest,
            'actor': row.actor, 'created_at': row.created_at}


@router.get('/api/projects/{project_id}/briefs')
def history(project_id: str, before: int | None = Query(default=None, ge=1),
            _: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    query = select(ProjectBriefVersion).where(ProjectBriefVersion.project_id == project_id)
    if before is not None:
        query = query.where(ProjectBriefVersion.revision < before)
    return [metadata(row) for row in db.scalars(query.order_by(
        ProjectBriefVersion.revision.desc()).limit(50))]


@router.get('/api/projects/{project_id}/briefs/{revision}')
def read_brief(project_id: str, revision: int,
               _: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    row = db.get(ProjectBriefVersion, (project_id, revision))
    if row is None:
        raise HTTPException(404, 'Brief revision not found')
    return {**metadata(row), 'content': row.content}


@router.put('/api/projects/{project_id}/brief')
def revise(project_id: str, data: BriefInput, session: OwnerSession = Depends(require_csrf),
           db: Session = Depends(db_session)):
    project = db.scalar(select(Project).where(Project.id == project_id).with_for_update()
                        .execution_options(populate_existing=True))
    if project is None:
        raise HTTPException(404, 'Project not found')
    if project.brief_revision != data.expected_revision:
        raise HTTPException(409, 'Brief changed. Reload the current brief before saving; your draft is retained.')
    project.brief_revision += 1
    project.objective = data.content
    row = add_version(db, project, session.owner_id)
    db.add(AuditEvent(actor=session.owner_id, action='project.brief.revise',
                      resource=f'{project_id}:{row.revision}', outcome='allowed'))
    record_activity(db, project_id=project_id, actor=session.owner_id,
                    action='project.brief.revise', resource=f'{project_id}:{row.revision}',
                    outcome='allowed')
    db.commit()
    return {**metadata(row), 'content': row.content}
