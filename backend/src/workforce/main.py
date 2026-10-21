from decimal import Decimal
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlparse
from .config import get_settings
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from .db import db_session
from .models import Agent, AgentConfigVersion, AgentProjectGrant, Approval, ArtifactVersion, AuditEvent, BudgetAccount, Execution, Outbox, OwnerSession, Project, ProjectActivityCursor, Task, now
from .security import clear_auth_cookies, current_session, login, require_csrf, require_origin, set_auth_cookies
from .services import AccessDenied, authorize_agent_project
from .task_graph import dependencies_satisfied
from .task_assignment import AssignmentError, assign_executor
from .cancellation import CancellationError, cancel_subtree
from .artifacts import proposal_valid
from .artifact_read import ArtifactIntegrityError, provenance, read_version
from . import providers
from .providers import ProviderError
from .activity import record_activity
from .project_briefs import add_version, router as brief_router
from .execution_briefs import BriefSourceError, attach_source, current_version, router as source_router

app = FastAPI(title='Workforce control plane', docs_url=None, redoc_url=None)
app.include_router(brief_router)
app.include_router(source_router)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlparse(get_settings().allowed_origin).hostname])


@app.middleware('http')
async def origin_middleware(request: Request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        try:
            require_origin(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})
    return await call_next(request)


class LoginInput(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    objective: str = Field(default='', max_length=20000)


class AgentInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1, max_length=20000)
    provider_connection: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=160)
    output_contract: Literal['text', 'collaboration.v1', 'memory.v1', 'tool.v1'] = 'text'


class TaskInput(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=240)


@app.get('/health/live')
def live():
    return {'status': 'live'}


@app.get('/health/ready')
def ready(db: Session = Depends(db_session)):
    db.execute(text('SELECT 1'))
    return {'status': 'ready'}


@app.post('/api/auth/login')
def login_route(data: LoginInput, response: Response, db: Session = Depends(db_session)):
    token, csrf = login(db, data.password)
    set_auth_cookies(response, token, csrf)
    return {'username': 'owner'}


@app.get('/api/auth/me')
def me(session: OwnerSession = Depends(current_session)):
    return {'username': 'owner', 'session_expires_at': session.expires_at}


@app.post('/api/auth/logout')
def logout(response: Response, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    session.revoked_at = now()
    db.add(AuditEvent(actor=session.owner_id, action='auth.logout', resource='owner', outcome='allowed'))
    db.commit()
    clear_auth_cookies(response)
    return {'status': 'logged_out'}


@app.get('/api/projects')
def list_projects(_: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    rows = db.scalars(select(Project).order_by(Project.created_at, Project.id)).all()
    return [{'id': row.id, 'name': row.name, 'objective': row.objective,
             'plan_revision': row.plan_revision, 'brief_revision': row.brief_revision} for row in rows]


@app.post('/api/projects', status_code=201)
def create_project(data: ProjectInput, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    row = Project(name=data.name, objective=data.objective)
    db.add(row)
    db.flush()
    add_version(db, row, session.owner_id)
    db.add(ProjectActivityCursor(project_id=row.id, sequence=0))
    db.add(AuditEvent(actor=session.owner_id, action='project.create', resource=row.id, outcome='allowed'))
    record_activity(db, project_id=row.id, actor=session.owner_id,
                    action='project.create', resource=row.id, outcome='allowed')
    db.commit()
    return {'id': row.id, 'name': row.name, 'objective': row.objective,
            'plan_revision': row.plan_revision, 'brief_revision': row.brief_revision}


@app.get('/api/agents')
def list_agents(_: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    rows = db.scalars(select(Agent).order_by(Agent.created_at, Agent.id)).all()
    result = []
    for row in rows:
        config = db.scalar(select(AgentConfigVersion).where(AgentConfigVersion.agent_id == row.id)
                           .order_by(AgentConfigVersion.version.desc()).limit(1))
        result.append({'id': row.id, 'name': row.name, 'role': row.role, 'status': row.status,
                       'provider_connection': config.provider_connection if config else None,
                       'model_id': config.model_id if config else None, 'config_version': config.version if config else None})
    return result


@app.post('/api/agents', status_code=201)
def create_agent(data: AgentInput, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    try:
        capabilities = providers.registry.get(data.provider_connection).describe_capabilities(data.model_id)
    except ProviderError as exc:
        raise HTTPException(422, str(exc)) from exc
    if data.output_contract in ('collaboration.v1', 'memory.v1', 'tool.v1') and not capabilities.structured_output:
        raise HTTPException(422, 'Selected model lacks validated structured output')
    agent = Agent(name=data.name, role=data.role)
    db.add(agent)
    db.flush()
    db.add(AgentConfigVersion(agent_id=agent.id, version=1, instructions=data.instructions,
                              provider_connection=data.provider_connection, model_id=data.model_id,
                              config={'output_contract': data.output_contract}))
    db.add(AuditEvent(actor=session.owner_id, action='agent.create', resource=agent.id, outcome='allowed'))
    db.commit()
    return {'id': agent.id, 'name': agent.name, 'role': agent.role, 'status': agent.status}


@app.get('/api/tasks')
def list_tasks(project_id: str, _: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.created_at, Task.id)).all()
    return [{'id': row.id, 'title': row.title, 'status': row.status, 'revision': row.revision} for row in rows]


@app.post('/api/tasks', status_code=201)
def create_task(data: TaskInput, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    if db.get(Project, data.project_id) is None:
        raise HTTPException(404, 'Project not found')
    row = Task(project_id=data.project_id, title=data.title)
    db.add(row)
    db.flush()
    db.add(AuditEvent(actor=session.owner_id, action='task.create', resource=row.id, outcome='allowed'))
    record_activity(db, project_id=data.project_id, actor=session.owner_id,
                    action='task.create', resource=row.id, outcome='allowed')
    db.commit()
    return {'id': row.id, 'title': row.title, 'status': row.status}


@app.get('/api/activity')
def activity(_: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(100)).all()
    return [{'id': row.id, 'actor': row.actor, 'action': row.action, 'resource': row.resource, 'outcome': row.outcome, 'created_at': row.created_at} for row in rows]


class GrantInput(BaseModel):
    project_id: str
    action: str = Field(pattern=r'^project\.execute$')
    allowed: bool


class DispatchInput(BaseModel):
    agent_id: str
    expected_brief_revision: int | None = Field(default=None, strict=True, ge=1)
    root_cap: Decimal = Field(ge=Decimal('0.010000'), max_digits=12, decimal_places=6)


@app.post('/api/agents/{agent_id}/grants', status_code=201)
def set_grant(agent_id: str, data: GrantInput, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    if db.get(Agent, agent_id) is None or db.get(Project, data.project_id) is None:
        raise HTTPException(404, 'Resource not found')
    row = db.scalar(select(AgentProjectGrant).where(AgentProjectGrant.agent_id == agent_id, AgentProjectGrant.project_id == data.project_id, AgentProjectGrant.action == data.action).with_for_update())
    if row is None:
        row = AgentProjectGrant(agent_id=agent_id, project_id=data.project_id, action=data.action, allowed=data.allowed)
        db.add(row)
    else:
        row.allowed = data.allowed
    db.add(AuditEvent(actor=session.owner_id, action='grant.set', resource=data.project_id, outcome='allowed', detail={'agent_id': agent_id, 'action': data.action, 'allowed': data.allowed}))
    db.commit()
    return {'agent_id': agent_id, 'project_id': data.project_id, 'action': data.action, 'allowed': data.allowed}


@app.post('/api/tasks/{task_id}/dispatch', status_code=202)
def dispatch(task_id: str, data: DispatchInput, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    hint = db.get(Task, task_id)
    if hint is None:
        raise HTTPException(404, 'Resource not found')
    try:
        source = current_version(db, hint.project_id, data.expected_brief_revision)
    except BriefSourceError as exc:
        raise HTTPException(409, str(exc)) from exc
    task = db.execute(select(Task).where(Task.id == task_id).with_for_update()
                      .execution_options(populate_existing=True)).scalar_one_or_none()
    agent = db.execute(select(Agent).where(Agent.id == data.agent_id).with_for_update()).scalar_one_or_none()
    if task is None or agent is None:
        raise HTTPException(404, 'Resource not found')
    if task.status != 'backlog':
        raise HTTPException(409, 'Task is already dispatched')
    try:
        authorize_agent_project(db, data.agent_id, task.project_id, 'project.execute')
    except AccessDenied:
        raise HTTPException(403, 'Project access denied')
    if not dependencies_satisfied(db, task.id):
        raise HTTPException(409, 'Task prerequisites are not completed')
    config = db.scalar(select(AgentConfigVersion).where(AgentConfigVersion.agent_id == data.agent_id).order_by(AgentConfigVersion.version.desc()).limit(1))
    if config is None:
        raise HTTPException(409, 'Agent has no configuration')
    try:
        assignment, created = assign_executor(db, task, data.agent_id, session.owner_id)
    except AssignmentError as exc:
        raise HTTPException(409, str(exc)) from exc
    if created:
        db.add(AuditEvent(actor=session.owner_id, action='task.assign', resource=task.id,
                          outcome='allowed', detail={'agent_id': assignment.agent_id}))
    execution = Execution(task_id=task.id, agent_id=data.agent_id, config_version_id=config.id, root_id='', workflow_id='')
    db.add(execution)
    db.flush()
    execution.root_id = execution.id
    attach_source(db, execution, source)
    execution.workflow_id = f'execution:{execution.id}'
    db.add(BudgetAccount(root_id=execution.id, cap=data.root_cap, reserved=Decimal('0'), spent=Decimal('0')))
    db.add(Outbox(kind='execution.dispatch', idempotency_key=execution.workflow_id, payload={'execution_id': execution.id}))
    db.add(AuditEvent(actor=session.owner_id, action='execution.dispatch', resource=execution.id, outcome='allowed'))
    record_activity(db, project_id=task.project_id, actor=session.owner_id,
                    action='execution.dispatch', resource=execution.id,
                    outcome='allowed')
    task.status = 'queued'
    task.revision += 1
    db.commit()
    return {'execution_id': execution.id, 'status': execution.status}


@app.get('/api/executions/{execution_id}')
def get_execution(execution_id: str, _: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    execution = db.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(404, 'Execution not found')
    return {'id': execution.id, 'task_id': execution.task_id, 'agent_id': execution.agent_id,
            'config_version_id': execution.config_version_id, 'status': execution.status, 'cancelled': execution.cancelled}


@app.post('/api/executions/{execution_id}/cancel')
def cancel_execution(execution_id: str, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    try:
        execution, changed = cancel_subtree(db, execution_id, session.owner_id)
    except CancellationError as exc:
        raise HTTPException(404, 'Execution not found') from exc
    record_activity(db, project_id=db.get(Task, execution.task_id).project_id,
                    actor=session.owner_id, action='execution.cancel',
                    resource=execution.id, outcome='allowed')
    db.commit()
    return {'id': execution.id, 'status': execution.status,
            'cancelled': execution.cancelled, 'cancelled_count': changed}


@app.get('/api/approvals')
def list_approvals(_: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    rows = db.scalars(select(Approval).where(
        Approval.status == 'pending', Approval.tool_invocation_id.is_(None))
        .order_by(Approval.expires_at).limit(100)).all()
    return [{'id': row.id, 'execution_id': row.execution_id, 'resource': row.resource, 'status': row.status,
             'expires_at': row.expires_at, 'payload_hash': row.payload_hash, 'content': row.payload.get('content')}
            for row in rows]


class ApprovalDecision(BaseModel):
    approved: bool
    payload_hash: str = Field(min_length=64, max_length=64)


@app.post('/api/approvals/{approval_id}/decision')
def decide_approval(approval_id: str, data: ApprovalDecision, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    approval = db.execute(select(Approval).where(Approval.id == approval_id).with_for_update()).scalar_one_or_none()
    if approval is None or approval.tool_invocation_id is not None:
        raise HTTPException(404, 'Approval not found')
    if approval.status != 'pending':
        raise HTTPException(409, 'Approval already decided')
    if data.payload_hash != approval.payload_hash:
        raise HTTPException(409, 'Proposal changed')
    if data.approved and not proposal_valid(db, approval):
        approval.status = 'invalidated'
        db.add(AuditEvent(actor=session.owner_id, action='artifact.approval', resource=approval.resource, outcome='invalidated'))
        db.commit()
        raise HTTPException(409, 'Proposal invalidated')
    approval.status = 'approved' if data.approved else 'rejected'
    if data.approved:
        approval.decision_payload_hash = approval.payload_hash
    db.add(AuditEvent(actor=session.owner_id, action='artifact.approval', resource=approval.resource,
                      outcome=approval.status, detail={'payload_hash': approval.payload_hash}))
    source = db.get(Execution, approval.execution_id)
    record_activity(db, project_id=db.get(Task, source.task_id).project_id,
                    actor=session.owner_id, action='artifact.approval',
                    resource=approval.resource, outcome=approval.status)
    db.commit()
    return {'id': approval.id, 'status': approval.status}


@app.get('/api/artifacts')
def list_artifacts(project_id: str, _: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, 'Project not found')
    rows = db.scalars(select(ArtifactVersion).where(ArtifactVersion.project_id == project_id)
                      .order_by(ArtifactVersion.artifact_id, ArtifactVersion.version)).all()
    return [{'id': row.id, 'artifact_id': row.artifact_id, 'version': row.version, 'parent_id': row.parent_id,
             'execution_id': row.execution_id, 'author': row.author, 'digest': row.digest,
             'mime_type': row.mime_type, 'size': row.size, 'created_at': row.created_at} for row in rows]


@app.get('/api/artifacts/versions/{version_id}')
def get_artifact_version(version_id: str, _: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    row = db.get(ArtifactVersion, version_id)
    if row is None:
        raise HTTPException(404, 'Artifact version not found')
    try:
        result = read_version(db, project_id=row.project_id, version_id=version_id)
    except ArtifactIntegrityError as exc:
        raise HTTPException(503, str(exc)) from exc
    if result is None:
        raise HTTPException(404, 'Artifact version not found')
    version, content = result
    return {**provenance(db, version), 'content': content.decode('utf-8')}


from .provider_api import router as provider_router  # noqa: E402
app.include_router(provider_router)
from .cost_reconciliation import router as cost_reconciliation_router  # noqa: E402
app.include_router(cost_reconciliation_router)
from .task_api import router as task_router  # noqa: E402
app.include_router(task_router)
from .plan_api import router as plan_router  # noqa: E402
app.include_router(plan_router)
from .delegation_api import router as delegation_router  # noqa: E402
app.include_router(delegation_router)
from .message_api import router as message_router  # noqa: E402
app.include_router(message_router)
from .collaboration_api import router as collaboration_router  # noqa: E402
app.include_router(collaboration_router)
from .memory_api import router as memory_router  # noqa: E402
app.include_router(memory_router)
from .tool_api import router as tool_router  # noqa: E402
app.include_router(tool_router)
from .tool_policy_api import router as tool_policy_router  # noqa: E402
app.include_router(tool_policy_router)
from .schedule_api import router as schedule_router  # noqa: E402
app.include_router(schedule_router)
from .activity import router as activity_router  # noqa: E402
app.include_router(activity_router)
from .read_observations import router as read_observations_router  # noqa: E402
app.include_router(read_observations_router)
from .read_grants import router as read_grants_router  # noqa: E402
app.include_router(read_grants_router)

from .runner_grants import router as runner_grants_router  # noqa: E402
app.include_router(runner_grants_router)
