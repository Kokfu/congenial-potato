"""Inert owner-pinned runner metadata. No launcher, Docker client or dispatch."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .activity import record_activity
from .db import db_session
from .models import Agent, AuditEvent, OwnerSession, Project, RunnerProfileGrant
from .reviewed_runner_contract import PROFILE, PROFILE_SHA256
from .security import current_session, require_csrf
from .services import AccessDenied, authorize_agent_project

router = APIRouter()
# Reviewed source pin, deliberately inert: importing product routes must not
# import or read the fixture executable. Tests compare this pin to reviewed code.
REVIEWED_JOB_SHA256 = '4e6adbfde662e67c2988f0859cc474ee8d5a6b0b3d632138452b2a300740b894'


class RunnerGrantDenied(ValueError):
    pass


class RunnerBinding(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, revalidate_instances='always')
    profile_id: Literal['synthetic.text-digest']
    profile_revision: int = Field(strict=True, ge=1, le=1)
    profile_sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')
    image_id: str = Field(strict=True, pattern=r'^sha256:[0-9a-f]{64}$')
    job_sha256: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')

    @field_validator('profile_sha256', 'job_sha256')
    @classmethod
    def reviewed_pin(cls, value, info):
        expected = PROFILE_SHA256 if info.field_name == 'profile_sha256' else REVIEWED_JOB_SHA256
        if value != expected:
            raise ValueError('Reviewed runner pin unavailable')
        return value


class RunnerGrantInput(RunnerBinding):
    project_id: UUID
    agent_id: UUID
    expires_at: datetime
    enabled: bool = Field(strict=True)
    expected_revision: int = Field(strict=True, ge=0)


def grant_metadata(row: RunnerProfileGrant) -> dict:
    return {key: getattr(row, key) for key in (
        'id', 'project_id', 'agent_id', 'profile_id', 'profile_revision',
        'profile_sha256', 'image_id', 'job_sha256', 'expires_at', 'enabled', 'revision')}


def _binding(value) -> RunnerBinding:
    try:
        return RunnerBinding.model_validate(value)
    except ValueError:
        raise RunnerGrantDenied('Reviewed runner binding unavailable') from None


def set_runner_grant(db: Session, *, data: RunnerGrantInput,
                     owner_id: str) -> RunnerProfileGrant:
    # Also revalidate trusted Python callers / model_copy, not only HTTP input.
    try:
        data = RunnerGrantInput.model_validate(data)
    except ValueError:
        raise RunnerGrantDenied('Runner grant input unavailable') from None
    if db.scalar(select(Project.id).where(Project.id == str(data.project_id))
                 .with_for_update()) is None:
        raise RunnerGrantDenied('Project unavailable')
    if db.get(Agent, str(data.agent_id)) is None:
        raise RunnerGrantDenied('Agent unavailable')
    row = db.scalar(select(RunnerProfileGrant).where(
        RunnerProfileGrant.project_id == str(data.project_id),
        RunnerProfileGrant.agent_id == str(data.agent_id),
        RunnerProfileGrant.profile_id == data.profile_id)
        .with_for_update().execution_options(populate_existing=True))
    if data.expected_revision != (row.revision if row else 0):
        raise RunnerGrantDenied('Runner grant revision changed')
    now = datetime.now(timezone.utc)  # after all lock waits
    if (data.expires_at.tzinfo is None or data.expires_at.utcoffset() is None or
            (data.enabled and not now < data.expires_at <= now + timedelta(days=30))):
        raise RunnerGrantDenied('Runner grant expiry unavailable')
    values = data.model_dump(exclude={'project_id', 'agent_id', 'expected_revision'})
    if row is None:
        row = RunnerProfileGrant(project_id=str(data.project_id),
            agent_id=str(data.agent_id), revision=1, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
        row.revision += 1
    db.flush()
    db.add(AuditEvent(actor=owner_id, action='runner.grant.set', resource=row.id,
        outcome='allowed', detail=grant_metadata(row) | {
            'expires_at': row.expires_at.isoformat()}))
    record_activity(db, project_id=row.project_id, actor=owner_id,
        action='runner.grant.set', resource=row.id,
        outcome='enabled' if row.enabled else 'disabled')
    return row


def active_runner_grant_record(db: Session, *, project_id: str, agent_id: str,
                               binding: RunnerBinding) -> RunnerProfileGrant:
    """Current exact pins plus execution grant; not approval or permission to run.

    Caller must retain transaction locks and later recheck policy, approval, root
    budget, cancellation and independent attempt admission before any effect.
    """
    binding = _binding(binding)
    try:
        authorize_agent_project(db, agent_id, project_id, 'project.execute')
    except AccessDenied as exc:
        raise RunnerGrantDenied('Runner grant unavailable') from exc
    agent = db.scalar(select(Agent).where(Agent.id == agent_id)
        .with_for_update().execution_options(populate_existing=True))
    row = db.scalar(select(RunnerProfileGrant).where(
        RunnerProfileGrant.project_id == project_id,
        RunnerProfileGrant.agent_id == agent_id,
        RunnerProfileGrant.profile_id == binding.profile_id)
        .with_for_update().execution_options(populate_existing=True))
    if (agent is None or agent.status != 'active' or row is None or not row.enabled
            or row.expires_at <= datetime.now(timezone.utc)
            or any(getattr(row, key) != value for key, value in binding.model_dump().items())):
        raise RunnerGrantDenied('Runner grant unavailable')
    return row


@router.get('/api/runner-profile')
def reviewed_runner_profile(_: OwnerSession = Depends(current_session)):
    return {'profile_id': PROFILE.profile_id, 'profile_revision': PROFILE.revision,
            'profile_sha256': PROFILE_SHA256, 'job_sha256': REVIEWED_JOB_SHA256}


@router.get('/api/runner-profile-grants')
def list_runner_grants(project_id: UUID,
                       _: OwnerSession = Depends(current_session),
                       db: Session = Depends(db_session)):
    if db.get(Project, str(project_id)) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(RunnerProfileGrant).where(
        RunnerProfileGrant.project_id == str(project_id))
        .order_by(RunnerProfileGrant.profile_id, RunnerProfileGrant.agent_id)
        .limit(200)).all()
    return [grant_metadata(row) for row in rows]


@router.post('/api/runner-profile-grants', status_code=201)
def upsert_runner_grant(data: RunnerGrantInput,
                       session: OwnerSession = Depends(require_csrf),
                       db: Session = Depends(db_session)):
    try:
        row = set_runner_grant(db, data=data, owner_id=session.owner_id)
    except RunnerGrantDenied as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return grant_metadata(row)
