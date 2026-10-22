"""Owner-requested, atomic setup; never dispatches or admits work."""
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from .db import db_session
from .security import require_csrf
from .models import (Agent, AgentConfigVersion, AgentProjectGrant, AuditEvent,
    OwnerSession, Project, ProjectActivityCursor, Task)
from .project_briefs import add_version
from .activity import record_activity

router = APIRouter()


class SetupInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120, pattern=r'\S')
    notes: str = Field(min_length=1, max_length=20000, pattern=r'\S')


@router.post('/api/document-fixtures', status_code=201)
def setup(data: SetupInput, session: OwnerSession = Depends(require_csrf),
          db: Session = Depends(db_session)):
    project = Project(name=data.name, objective=data.notes)
    target = Agent(name=f'{data.name} drafter', role='specialist')
    manager = Agent(name=f'{data.name} planner', role='Manager')
    db.add_all([project, target, manager])
    db.flush()
    add_version(db, project, session.owner_id)
    db.add(ProjectActivityCursor(project_id=project.id, sequence=0))
    candidate = {'kind': 'plan', 'proposal_key': f'document-{project.id}',
        'expected_revision': 1, 'tasks': [
            {'work_key': 'draft', 'title': 'Prepare a cited draft',
             'assignee_id': target.id, 'depends_on': []},
            {'work_key': 'review', 'title': 'Review source citations',
             'assignee_id': target.id, 'depends_on': ['draft']}]}
    db.add_all([
        AgentConfigVersion(agent_id=target.id, version=1, instructions='Synthetic only',
            provider_connection='fixture', model_id='fake-v1', config={'output_contract': 'text'}),
        AgentConfigVersion(agent_id=manager.id, version=1,
            instructions='FIXTURE_COLLAB_JSON:' + json.dumps(candidate),
            provider_connection='fixture-collaboration', model_id='collaboration-v1',
            config={'output_contract': 'collaboration.v1'})])
    for agent in (target, manager):
        db.add(AgentProjectGrant(agent_id=agent.id, project_id=project.id,
            action='project.execute', allowed=True))
    task = Task(project_id=project.id, title='Propose fixture document plan')
    db.add(task)
    db.flush()
    db.add(AuditEvent(actor=session.owner_id, action='document.fixture.setup',
        resource=project.id, outcome='allowed'))
    record_activity(db, project_id=project.id, actor=session.owner_id,
        action='document.fixture.setup', resource=project.id, outcome='allowed')
    db.commit()
    return {'project_id': project.id, 'manager_id': manager.id,
        'draft_agent_id': target.id, 'task_id': task.id}
