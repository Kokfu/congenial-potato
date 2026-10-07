from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Owner(Base):
    __tablename__ = 'owners'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OwnerSession(Base):
    __tablename__ = 'owner_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('owners.id'))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    objective: Mapped[str] = mapped_column(Text, default='')
    plan_revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Agent(Base):
    __tablename__ = 'agents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentConfigVersion(Base):
    __tablename__ = 'agent_config_versions'
    __table_args__ = (UniqueConstraint('agent_id', 'version'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    agent_id: Mapped[str] = mapped_column(ForeignKey('agents.id'))
    version: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str] = mapped_column(Text)
    provider_connection: Mapped[str] = mapped_column(String(120))
    model_id: Mapped[str] = mapped_column(String(160))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentProjectGrant(Base):
    __tablename__ = 'agent_project_grants'
    __table_args__ = (UniqueConstraint('agent_id', 'project_id', 'action'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    agent_id: Mapped[str] = mapped_column(ForeignKey('agents.id'))
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    action: Mapped[str] = mapped_column(String(60))
    allowed: Mapped[bool] = mapped_column(Boolean, default=False)


class Task(Base):
    __tablename__ = 'tasks'
    __table_args__ = (UniqueConstraint('project_id', 'work_key', name='uq_task_project_work_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('tasks.id'))
    title: Mapped[str] = mapped_column(String(240))
    work_key: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default='backlog')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TaskDependency(Base):
    __tablename__ = 'task_dependencies'
    __table_args__ = (
        UniqueConstraint('prerequisite_id', 'dependent_id'),
        CheckConstraint('prerequisite_id <> dependent_id', name='ck_task_dependency_distinct'),
        Index('ix_task_dependencies_dependent_id', 'dependent_id'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    prerequisite_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'))
    dependent_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TaskAssignment(Base):
    __tablename__ = 'task_assignments'
    __table_args__ = (UniqueConstraint('task_id', name='uq_task_assignment_task'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'))
    agent_id: Mapped[str] = mapped_column(ForeignKey('agents.id'))
    assigned_by: Mapped[str] = mapped_column(ForeignKey('owners.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PlanProposal(Base):
    __tablename__ = 'plan_proposals'
    __table_args__ = (UniqueConstraint('source_execution_id', 'proposal_key',
                                       name='uq_plan_source_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    source_execution_id: Mapped[str] = mapped_column(ForeignKey('executions.id'))
    submitted_by: Mapped[str] = mapped_column(ForeignKey('owners.id'))
    proposal_key: Mapped[str] = mapped_column(String(100))
    expected_revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default='proposed')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Execution(Base):
    __tablename__ = 'executions'
    __table_args__ = (UniqueConstraint('parent_id', 'delegation_key', name='uq_execution_delegation_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'))
    agent_id: Mapped[str] = mapped_column(ForeignKey('agents.id'))
    config_version_id: Mapped[str] = mapped_column(ForeignKey('agent_config_versions.id'))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('executions.id'))
    delegation_key: Mapped[str | None] = mapped_column(String(100))
    delegation_hash: Mapped[str | None] = mapped_column(String(64))
    depth: Mapped[int] = mapped_column(Integer, default=0)
    root_id: Mapped[str] = mapped_column(String(36))
    workflow_id: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(30), default='queued')
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PolicyRule(Base):
    __tablename__ = 'policy_rules'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(100))
    resource: Mapped[str] = mapped_column(String(240))
    effect: Mapped[str] = mapped_column(String(30))
    revision: Mapped[int] = mapped_column(Integer, default=1)


class Approval(Base):
    __tablename__ = 'approvals'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    execution_id: Mapped[str] = mapped_column(ForeignKey('executions.id'))
    invocation_key: Mapped[str] = mapped_column(String(160), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    decision_payload_hash: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    schema_hash: Mapped[str] = mapped_column(String(64))
    resource: Mapped[str] = mapped_column(String(240))
    target_version: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default='pending')
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArtifactVersion(Base):
    __tablename__ = 'artifact_versions'
    __table_args__ = (UniqueConstraint('artifact_id', 'version'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    artifact_id: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    version: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('artifact_versions.id'))
    execution_id: Mapped[str | None] = mapped_column(ForeignKey('executions.id'))
    author: Mapped[str] = mapped_column(String(160))
    digest: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    storage_ref: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BudgetAccount(Base):
    __tablename__ = 'budget_accounts'
    root_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cap: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    spent: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    currency: Mapped[str] = mapped_column(String(3), default='USD')


class DailyBudgetAccount(Base):
    __tablename__ = 'daily_budget_accounts'
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    cap: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    spent: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    currency: Mapped[str] = mapped_column(String(3), default='USD')


class BudgetReservation(Base):
    __tablename__ = 'budget_reservations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    root_id: Mapped[str] = mapped_column(ForeignKey('budget_accounts.root_id'))
    invocation_key: Mapped[str] = mapped_column(String(160), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    daily_day: Mapped[date | None] = mapped_column(ForeignKey('daily_budget_accounts.day'))
    actual: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    status: Mapped[str] = mapped_column(String(30), default='reserved')


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    __table_args__ = (UniqueConstraint('effect_key', name='uq_audit_events_effect_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(120))
    resource: Mapped[str] = mapped_column(String(240))
    outcome: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    effect_key: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Outbox(Base):
    __tablename__ = 'outbox'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    payload: Mapped[dict] = mapped_column(JSON)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelCall(Base):
    __tablename__ = 'model_calls'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    execution_id: Mapped[str] = mapped_column(ForeignKey('executions.id'), unique=True)
    provider: Mapped[str] = mapped_column(String(120))
    model_id: Mapped[str] = mapped_column(String(160))
    provider_request_id: Mapped[str | None] = mapped_column(String(240))
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
