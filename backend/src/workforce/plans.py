"""Deterministic admission of small, synthetic Manager plan candidates."""
import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Agent, AuditEvent, Execution, PlanProposal, Project, Task, TaskDependency
from .services import AccessDenied, authorize_agent_project
from .task_assignment import assign_executor


class PlanTask(BaseModel):
    model_config = ConfigDict(extra='forbid')
    work_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    title: str = Field(min_length=1, max_length=240)
    assignee_id: str
    depends_on: list[str] = Field(default_factory=list, max_length=11)


class PlanInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_execution_id: str
    proposal_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    expected_revision: int = Field(ge=1)
    tasks: list[PlanTask] = Field(min_length=1, max_length=12)


class PlanError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def plan_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_plan(db: Session, project_id: str, data: PlanInput) -> None:
    execution = db.get(Execution, data.source_execution_id)
    if execution is None or execution.status != 'succeeded' or execution.cancelled:
        raise PlanError('source_unavailable')
    source_task = db.get(Task, execution.task_id)
    agent = db.get(Agent, execution.agent_id)
    if source_task is None or source_task.project_id != project_id or agent is None or agent.role.lower() != 'manager':
        raise PlanError('source_scope')
    authorize_agent_project(db, agent.id, project_id, 'project.execute')
    keys = [item.work_key for item in data.tasks]
    if len(set(keys)) != len(keys):
        raise PlanError('duplicate_work_key')
    existing = db.scalar(select(Task.id).where(Task.project_id == project_id,
                                               Task.work_key.in_(keys)).limit(1))
    if existing is not None:
        raise PlanError('work_already_exists')
    dependencies = {item.work_key: item.depends_on for item in data.tasks}
    if any(len(set(deps)) != len(deps) or any(dep not in dependencies or dep == key for dep in deps)
           for key, deps in dependencies.items()):
        raise PlanError('invalid_dependency')
    seen: set[str] = set()
    visiting: set[str] = set()
    def visit(key: str) -> None:
        if key in visiting:
            raise PlanError('cycle')
        if key in seen:
            return
        visiting.add(key)
        for dependency in dependencies[key]:
            visit(dependency)
        visiting.remove(key)
        seen.add(key)
    for key in dependencies:
        visit(key)
    for item in data.tasks:
        assignee = db.get(Agent, item.assignee_id)
        if assignee is None or assignee.status != 'active':
            raise PlanError('assignee_unavailable')
        authorize_agent_project(db, assignee.id, project_id, 'project.execute')


def propose(db: Session, project_id: str, data: PlanInput, owner_id: str) -> tuple[PlanProposal, bool]:
    project = db.execute(select(Project).where(Project.id == project_id).with_for_update()).scalar_one_or_none()
    if project is None:
        raise PlanError('project_missing')
    payload = data.model_dump(mode='json')
    digest = plan_hash(payload)
    existing = db.scalar(select(PlanProposal).where(
        PlanProposal.source_execution_id == data.source_execution_id,
        PlanProposal.proposal_key == data.proposal_key))
    if existing is not None:
        if existing.project_id != project_id or existing.payload_hash != digest:
            raise PlanError('proposal_key_reused')
        return existing, False
    if project.plan_revision != data.expected_revision:
        raise PlanError('project_revision_changed')
    validate_plan(db, project_id, data)
    proposal = PlanProposal(project_id=project_id,
                            source_execution_id=data.source_execution_id,
                            submitted_by=owner_id, proposal_key=data.proposal_key,
                            expected_revision=data.expected_revision, payload=payload,
                            payload_hash=digest, status='proposed')
    db.add(proposal)
    db.flush()
    db.add(AuditEvent(actor=owner_id, action='plan.propose', resource=proposal.id,
                      outcome='recorded', detail={'source_execution_id': data.source_execution_id,
                                                  'payload_hash': digest}))
    return proposal, True


def admit(db: Session, proposal_id: str, expected_hash: str, owner_id: str) -> PlanProposal:
    # Project lock serializes admission and work-key checks across proposals.
    candidate = db.get(PlanProposal, proposal_id)
    if candidate is None:
        raise PlanError('proposal_missing')
    project = db.execute(select(Project).where(Project.id == candidate.project_id).with_for_update()).scalar_one()
    proposal = db.execute(select(PlanProposal).where(PlanProposal.id == proposal_id).with_for_update()).scalar_one()
    if proposal.payload_hash != expected_hash or plan_hash(proposal.payload) != expected_hash:
        raise PlanError('proposal_changed')
    if proposal.status == 'admitted':
        return proposal
    if proposal.status != 'proposed' or project.plan_revision != proposal.expected_revision:
        raise PlanError('project_revision_changed')
    data = PlanInput.model_validate(proposal.payload)
    validate_plan(db, project.id, data)
    tasks: dict[str, Task] = {}
    for item in data.tasks:
        task = Task(project_id=project.id, title=item.title, work_key=item.work_key)
        db.add(task)
        db.flush()
        assignment, _ = assign_executor(db, task, item.assignee_id, owner_id)
        db.add(AuditEvent(actor=owner_id, action='task.assign', resource=task.id,
                          outcome='allowed', detail={'agent_id': assignment.agent_id,
                                                     'proposal_id': proposal.id}))
        tasks[item.work_key] = task
    for item in data.tasks:
        for prerequisite in item.depends_on:
            db.add(TaskDependency(project_id=project.id,
                                  prerequisite_id=tasks[prerequisite].id,
                                  dependent_id=tasks[item.work_key].id))
    proposal.status = 'admitted'
    project.plan_revision += 1
    db.add(AuditEvent(actor=owner_id, action='plan.admit', resource=proposal.id,
                      outcome='allowed', detail={'task_ids': [task.id for task in tasks.values()],
                                                 'payload_hash': expected_hash}))
    return proposal
