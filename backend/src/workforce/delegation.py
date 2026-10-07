"""One bounded delegation service for Manager and specialist sources."""
import hashlib
import json
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (Agent, AgentConfigVersion, AuditEvent, BudgetAccount,
                     Execution, Outbox, Project, Task)
from .services import AccessDenied, authorize_agent_project
from .task_assignment import assign_executor

MAX_DEPTH = 3
MAX_CHILDREN = 4
MAX_ROOT_EXECUTIONS = 12
MIN_CALL_HOLD = Decimal('0.010000')


class DelegationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    work_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    title: str = Field(min_length=1, max_length=240)
    agent_id: str


class DelegationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def payload_hash(data: DelegationInput) -> str:
    payload = data.model_dump(mode='json')
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def delegate(db: Session, parent_id: str, data: DelegationInput,
             owner_id: str) -> tuple[Execution, bool]:
    parent_hint = db.get(Execution, parent_id)
    if parent_hint is None:
        raise DelegationError('source_missing')
    parent_task_hint = db.get(Task, parent_hint.task_id)
    # Serialize work keys, delegation counts and root checks in one project.
    db.execute(select(Project).where(Project.id == parent_task_hint.project_id)
               .with_for_update()).scalar_one()
    parent = db.execute(select(Execution).where(Execution.id == parent_id)
                        .with_for_update()).scalar_one()
    source_task = db.get(Task, parent.task_id)
    digest = payload_hash(data)
    existing = db.scalar(select(Execution).where(
        Execution.parent_id == parent.id,
        Execution.delegation_key == data.request_key))
    if existing is not None:
        if existing.delegation_hash != digest:
            raise DelegationError('request_key_reused')
        return existing, False
    if parent.cancelled or parent.status not in ('running', 'succeeded'):
        raise DelegationError('source_unavailable')
    source_agent = db.get(Agent, parent.agent_id)
    if source_agent is None or source_agent.role.lower() not in ('manager', 'specialist'):
        raise DelegationError('source_role')
    if parent.depth >= MAX_DEPTH:
        raise DelegationError('depth_limit')
    root = db.execute(select(Execution).where(Execution.id == parent.root_id)
                      .with_for_update()).scalar_one_or_none()
    if root is None or root.cancelled:
        raise DelegationError('root_cancelled')
    account = db.execute(select(BudgetAccount).where(BudgetAccount.root_id == root.id)
                         .with_for_update()).scalar_one_or_none()
    if account is None or account.cap - account.spent - account.reserved < MIN_CALL_HOLD:
        raise DelegationError('root_budget_unavailable')
    child_count = db.scalar(select(func.count(Execution.id)).where(Execution.parent_id == parent.id))
    root_count = db.scalar(select(func.count(Execution.id)).where(Execution.root_id == root.id))
    if child_count >= MAX_CHILDREN or root_count >= MAX_ROOT_EXECUTIONS:
        raise DelegationError('execution_limit')
    if db.scalar(select(Task.id).where(Task.project_id == source_task.project_id,
                                       Task.work_key == data.work_key).limit(1)) is not None:
        raise DelegationError('work_already_exists')
    target = db.get(Agent, data.agent_id)
    if target is None or target.status != 'active':
        raise DelegationError('assignee_unavailable')
    authorize_agent_project(db, parent.agent_id, source_task.project_id, 'project.execute')
    authorize_agent_project(db, target.id, source_task.project_id, 'project.execute')
    config = db.scalar(select(AgentConfigVersion).where(
        AgentConfigVersion.agent_id == target.id)
        .order_by(AgentConfigVersion.version.desc()).limit(1))
    if config is None:
        raise DelegationError('assignee_unconfigured')
    task = Task(project_id=source_task.project_id, parent_id=source_task.id,
                work_key=data.work_key, title=data.title)
    db.add(task)
    db.flush()
    assign_executor(db, task, target.id, owner_id)
    task.status = 'queued'
    task.revision += 1
    child = Execution(task_id=task.id, agent_id=target.id, config_version_id=config.id,
                      parent_id=parent.id, delegation_key=data.request_key,
                      delegation_hash=digest, depth=parent.depth + 1,
                      root_id=root.id, workflow_id='')
    db.add(child)
    db.flush()
    child.workflow_id = f'execution:{child.id}'
    db.add(Outbox(kind='execution.dispatch', idempotency_key=child.workflow_id,
                  payload={'execution_id': child.id}))
    db.add(AuditEvent(actor=owner_id, action='execution.delegate', resource=child.id,
                      outcome='allowed', detail={'parent_id': parent.id,
                                                 'root_id': root.id, 'work_key': data.work_key,
                                                 'payload_hash': digest}))
    return child, True
