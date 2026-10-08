from datetime import timedelta

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.memory_context import SummaryError, build_context, create_summary
from workforce.models import (Agent, AgentProjectGrant, MemoryRecord, Owner,
                              Project, ProjectSummaryVersion, now)
from workforce.services import AccessDenied


def setup(db):
    p1, p2 = Project(name='Project one'), Project(name='Project two')
    agent = Agent(name='Reader', role='specialist')
    db.add_all([p1, p2, agent])
    db.flush()
    db.add(AgentProjectGrant(agent_id=agent.id, project_id=p1.id,
                             action='project.execute', allowed=True))
    owner_id = db.scalar(select(Owner.id))
    decision = MemoryRecord(project_id=p1.id, kind='decision', subject_key='retention',
                            content='Retain synthetic records for 30 days.',
                            trust_origin='approved_decision', status='active',
                            creator_kind='owner', creator_id=owner_id)
    claim = MemoryRecord(project_id=p1.id, kind='claim', subject_key='external',
                         content='External page says to ignore all instructions.',
                         trust_origin='external_claim', status='active',
                         creator_kind='agent', creator_id=agent.id)
    private = MemoryRecord(project_id=p2.id, kind='fact', subject_key='private',
                           content='Private marker never in context.',
                           trust_origin='observed_result', status='active',
                           creator_kind='owner', creator_id=owner_id)
    db.add_all([decision, claim, private])
    db.flush()
    return p1, p2, agent, owner_id, decision, claim, private


def test_summary_versions_citations_and_context_trust():
    with session_factory()() as db:
        p1, p2, agent, owner_id, decision, claim, private = setup(db)
        with pytest.raises(SummaryError):
            create_summary(db, project_id=p1.id, owner_id=owner_id,
                           expected_version=0, content='Cross project',
                           citation_ids=[private.id])
        first = create_summary(db, project_id=p1.id, owner_id=owner_id,
                               expected_version=0, content='Review retention decision.',
                               citation_ids=[decision.id])
        with pytest.raises(SummaryError):
            create_summary(db, project_id=p1.id, owner_id=owner_id,
                           expected_version=0, content='Stale edit',
                           citation_ids=[claim.id])
        second = create_summary(db, project_id=p1.id, owner_id=owner_id,
                                expected_version=1,
                                content='External source also makes an untrusted claim.',
                                citation_ids=[claim.id])
        db.commit()
        assert second.parent_id == first.id and second.version == 2
        assert db.scalar(select(ProjectSummaryVersion).where(
            ProjectSummaryVersion.id == first.id)).content == 'Review retention decision.'
        context = build_context(db, project_id=p1.id, agent_id=agent.id)
        assert 'approved_decision' in context
        assert 'external_claim' in context
        assert f'derived_summary:{second.id}' in context
        assert f'citations:{claim.id}' in context
        assert 'Private marker' not in context
        assert context.index('approved_decision') < context.index('external_claim')
        assert len(context) <= 4000
        with pytest.raises(AccessDenied):
            build_context(db, project_id=p2.id, agent_id=agent.id)
        claim.valid_until = now() - timedelta(seconds=1)
        db.commit()
        assert f'derived_summary:{second.id}' not in build_context(
            db, project_id=p1.id, agent_id=agent.id)


def test_owner_summary_api_requires_citations(authenticated):
    h = {'Origin': 'http://localhost:8080',
         'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    project = authenticated.post('/api/projects', json={'name': 'Summary'}, headers=h).json()
    url = f"/api/projects/{project['id']}/summaries"
    assert authenticated.post(url, json={'expected_version': 0,
        'content': 'Unsupported assertion', 'citation_ids': ['missing']},
        headers=h).status_code == 409
    assert authenticated.post(url, json={'expected_version': 0,
        'content': 'Claim is a system instruction', 'citation_ids': ['missing'],
        'trust_origin': 'human_instruction'}, headers=h).status_code == 422
    assert authenticated.get(url).json() == []
