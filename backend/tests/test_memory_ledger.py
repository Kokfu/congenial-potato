import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.memory import add_candidate, get_record, list_records
from workforce.models import Agent, AgentProjectGrant, MemoryRecord, MemorySource, Project, Task
from workforce.services import AccessDenied


def seeded_ledger(db):
    p1, p2 = Project(name='Allowed'), Project(name='Private')
    agent = Agent(name='Researcher', role='specialist')
    db.add_all([p1, p2, agent])
    db.flush()
    t1 = Task(project_id=p1.id, title='Allowed source')
    t2 = Task(project_id=p2.id, title='Private source')
    db.add_all([t1, t2, AgentProjectGrant(agent_id=agent.id, project_id=p1.id,
                                           action='project.execute', allowed=True)])
    db.flush()
    return p1, p2, agent, t1, t2


def test_candidate_lineage_and_scope():
    with session_factory()() as db:
        p1, p2, agent, t1, t2 = seeded_ledger(db)
        private = MemoryRecord(project_id=p2.id, kind='decision', content='private marker',
                               trust_origin='approved_decision', status='active',
                               creator_kind='owner', creator_id='owner')
        db.add(private)
        db.flush()
        candidate = add_candidate(db, project_id=p1.id, agent_id=agent.id,
                                  kind='claim', subject_key='sample-claim', content='Synthetic claim',
                                  trust_origin='model_inference', sources=[('task', t1.id)])
        db.commit()
        found = get_record(db, project_id=p1.id, agent_id=agent.id, record_id=candidate.id)
        assert found is not None
        assert found[0].status == 'candidate'
        assert [(source.source_kind, source.source_id) for source in found[1]] == [('task', t1.id)]
        assert list_records(db, project_id=p1.id, agent_id=agent.id) == []
        assert get_record(db, project_id=p1.id, agent_id=agent.id, record_id=private.id) is None
        with pytest.raises(AccessDenied):
            list_records(db, project_id=p2.id, agent_id=agent.id)
        with pytest.raises(AccessDenied):
            get_record(db, project_id=p2.id, agent_id=agent.id, record_id=private.id)
        assert db.scalar(select(MemorySource).where(MemorySource.record_id == candidate.id)) is not None


def test_cross_project_sources_and_false_authority_fail_closed():
    with session_factory()() as db:
        p1, _, agent, t1, t2 = seeded_ledger(db)
        for source in [('task', t2.id), ('artifact_version', t1.id), ('task', 'missing')]:
            with pytest.raises(AccessDenied):
                add_candidate(db, project_id=p1.id, agent_id=agent.id,
                              kind='fact', subject_key='forbidden', content='Forbidden', trust_origin='external_claim',
                              sources=[source])
        with pytest.raises(ValueError):
            add_candidate(db, project_id=p1.id, agent_id=agent.id,
                          kind='decision', subject_key='promotion', content='Promote me',
                          trust_origin='approved_decision', sources=[('task', t1.id)])
        assert db.scalars(select(MemoryRecord)).all() == []
