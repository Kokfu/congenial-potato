from datetime import timedelta

import pytest

from workforce.db import session_factory
from workforce.memory_search import search_records
from workforce.models import Agent, AgentProjectGrant, MemoryRecord, Project, now
from workforce.services import AccessDenied


def record(project_id, subject, content, status='active', valid_until=None):
    return MemoryRecord(project_id=project_id, kind='fact', subject_key=subject,
                        content=content, trust_origin='observed_result',
                        creator_kind='owner', creator_id='synthetic-owner',
                        status=status, valid_until=valid_until)


def test_scoped_search_prioritizes_relevant_current_records():
    with session_factory()() as db:
        allowed, private = Project(name='Allowed'), Project(name='Private')
        agent = Agent(name='Reader', role='specialist')
        db.add_all([allowed, private, agent])
        db.flush()
        db.add(AgentProjectGrant(agent_id=agent.id, project_id=allowed.id,
                                 action='project.execute', allowed=True))
        db.add_all([
            record(allowed.id, 'retention-rule', 'The required retention period is 30 days.'),
            record(allowed.id, 'meeting-note', 'Unrelated lunch conversation.'),
            record(allowed.id, 'expired-rule', 'The old retention period is 90 days.',
                   valid_until=now() - timedelta(days=1)),
            record(allowed.id, 'unreviewed-rule', 'Candidate retention is forever.',
                   status='candidate'),
            record(allowed.id, 'superseded-rule', 'Superseded retention is 60 days.',
                   status='superseded'),
            record(private.id, 'private-rule', 'Secret retention period is 5 days.'),
        ])
        db.commit()
        hits = search_records(db, project_id=allowed.id, agent_id=agent.id,
                              query='retention period', limit=5)
        assert len(hits) == 1
        assert hits[0].subject_key == 'retention-rule'
        assert '30 days' in hits[0].snippet
        assert hits[0].project_id == allowed.id
        assert len(hits[0].snippet) <= 242
        with pytest.raises(AccessDenied):
            search_records(db, project_id=private.id, agent_id=agent.id,
                           query='Secret retention')
        assert search_records(db, project_id=allowed.id, agent_id=agent.id,
                              query='Secret retention') == []


def test_search_bounds_fail_closed():
    with session_factory()() as db:
        project = Project(name='Allowed')
        agent = Agent(name='Reader', role='specialist')
        db.add_all([project, agent])
        db.flush()
        db.add(AgentProjectGrant(agent_id=agent.id, project_id=project.id,
                                 action='project.execute', allowed=True))
        db.commit()
        for query, limit in [('', 10), ('x' * 201, 10), ('x', 0), ('x', 51)]:
            with pytest.raises(ValueError):
                search_records(db, project_id=project.id, agent_id=agent.id,
                               query=query, limit=limit)
