from decimal import Decimal
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlparse
from .config import get_settings
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from .db import db_session
from .models import Agent, AgentConfigVersion, AgentProjectGrant, AuditEvent, BudgetAccount, Execution, Outbox, OwnerSession, Project, Task, now
from .security import clear_auth_cookies, current_session, login, require_csrf, require_origin, set_auth_cookies
from .services import AccessDenied, authorize_agent_project

app = FastAPI(title='Workforce control plane', docs_url=None, redoc_url=None)
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
    return [{'id': row.id, 'name': row.name, 'objective': row.objective} for row in rows]


@app.post('/api/projects', status_code=201)
def create_project(data: ProjectInput, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    row = Project(name=data.name, objective=data.objective)
    db.add(row)
    db.flush()
    db.add(AuditEvent(actor=session.owner_id, action='project.create', resource=row.id, outcome='allowed'))
    db.commit()
    return {'id': row.id, 'name': row.name, 'objective': row.objective}


@app.get('/api/agents')
def list_agents(_: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    rows = db.scalars(select(Agent).order_by(Agent.created_at, Agent.id)).all()
    return [{'id': row.id, 'name': row.name, 'role': row.role, 'status': row.status} for row in rows]


@app.post('/api/agents', status_code=201)
def create_agent(data: AgentInput, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    agent = Agent(name=data.name, role=data.role)
    db.add(agent)
    db.flush()
    db.add(AgentConfigVersion(agent_id=agent.id, version=1, instructions=data.instructions, provider_connection=data.provider_connection, model_id=data.model_id))
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
    root_cap: Decimal = Field(ge=Decimal('0.010000'), max_digits=12, decimal_places=6)


@app.post('/api/agents/{agent_id}/grants', status_code=201)
def set_grant(agent_id: str, data: GrantInput, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    if db.get(Agent, agent_id) is None or db.get(Project, data.project_id) is None:
        raise HTTPException(404, 'Resource not found')
    row = db.scalar(select(AgentProjectGrant).where(AgentProjectGrant.agent_id == agent_id, AgentProjectGrant.project_id == data.project_id, AgentProjectGrant.action == data.action))
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
    task = db.execute(select(Task).where(Task.id == task_id).with_for_update()).scalar_one_or_none()
    if task is None or db.get(Agent, data.agent_id) is None:
        raise HTTPException(404, 'Resource not found')
    if task.status != 'backlog':
        raise HTTPException(409, 'Task is already dispatched')
    try:
        authorize_agent_project(db, data.agent_id, task.project_id, 'project.execute')
    except AccessDenied:
        raise HTTPException(403, 'Project access denied')
    config = db.scalar(select(AgentConfigVersion).where(AgentConfigVersion.agent_id == data.agent_id).order_by(AgentConfigVersion.version.desc()).limit(1))
    if config is None:
        raise HTTPException(409, 'Agent has no configuration')
    execution = Execution(task_id=task.id, agent_id=data.agent_id, config_version_id=config.id, root_id='', workflow_id='')
    db.add(execution)
    db.flush()
    execution.root_id = execution.id
    execution.workflow_id = f'execution:{execution.id}'
    db.add(BudgetAccount(root_id=execution.id, cap=data.root_cap, reserved=Decimal('0'), spent=Decimal('0')))
    db.add(Outbox(kind='execution.dispatch', idempotency_key=execution.workflow_id, payload={'execution_id': execution.id}))
    db.add(AuditEvent(actor=session.owner_id, action='execution.dispatch', resource=execution.id, outcome='allowed'))
    task.status = 'queued'
    db.commit()
    return {'execution_id': execution.id, 'status': execution.status}


@app.get('/api/executions/{execution_id}')
def get_execution(execution_id: str, _: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    execution = db.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(404, 'Execution not found')
    return {'id': execution.id, 'task_id': execution.task_id, 'agent_id': execution.agent_id, 'status': execution.status, 'cancelled': execution.cancelled}


@app.post('/api/executions/{execution_id}/cancel')
def cancel_execution(execution_id: str, session: OwnerSession = Depends(require_csrf), db: Session = Depends(db_session)):
    execution = db.execute(select(Execution).where(Execution.id == execution_id).with_for_update()).scalar_one_or_none()
    if execution is None:
        raise HTTPException(404, 'Execution not found')
    if execution.status == 'succeeded':
        raise HTTPException(409, 'Execution already succeeded')
    execution.cancelled = True
    execution.status = 'cancelled'
    db.add(AuditEvent(actor=session.owner_id, action='execution.cancel', resource=execution.id, outcome='allowed'))
    db.commit()
    return {'id': execution.id, 'status': execution.status}


@app.get('/api/approvals')
def list_approvals(_: OwnerSession = Depends(current_session), db: Session = Depends(db_session)):
    from .models import Approval
    rows = db.scalars(select(Approval).where(Approval.status == 'pending').order_by(Approval.expires_at).limit(100)).all()
    return [{'id': row.id, 'execution_id': row.execution_id, 'resource': row.resource, 'status': row.status, 'expires_at': row.expires_at} for row in rows]
