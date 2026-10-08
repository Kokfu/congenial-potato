from sqlalchemy import select

from workforce.db import session_factory
from workforce.memory import get_record
from workforce.memory_context import build_context, create_summary
from workforce.memory_search import search_records
from workforce.models import Agent, AgentProjectGrant, MemoryRecord, Owner, Project


def test_explicit_supersession_preserves_history_and_stales_summary(authenticated):
    h = {'Origin': 'http://localhost:8080',
         'X-CSRF-Token': authenticated.cookies['workforce_csrf']}
    with session_factory()() as db:
        project, private = Project(name='Records'), Project(name='Private')
        agent = Agent(name='Reader', role='specialist')
        db.add_all([project, private, agent])
        db.flush()
        db.add(AgentProjectGrant(agent_id=agent.id, project_id=project.id,
                                 action='project.execute', allowed=True))
        owner_id = db.scalar(select(Owner.id))
        old = MemoryRecord(project_id=project.id, kind='fact', subject_key='retention',
                           content='Retention is 90 days', trust_origin='observed_result',
                           status='active', creator_kind='owner', creator_id=owner_id)
        new = MemoryRecord(project_id=project.id, kind='fact', subject_key='retention',
                           content='Retention is 30 days', trust_origin='observed_result',
                           status='active', creator_kind='owner', creator_id=owner_id)
        foreign = MemoryRecord(project_id=private.id, kind='fact', subject_key='retention',
                               content='Private retention is 5 days',
                               trust_origin='observed_result', status='active',
                               creator_kind='owner', creator_id=owner_id)
        db.add_all([old, new, foreign])
        db.flush()
        summary = create_summary(db, project_id=project.id, owner_id=owner_id,
                                 expected_version=0, content='Old retention summary',
                                 citation_ids=[old.id])
        project_id, agent_id = project.id, agent.id
        old_id, new_id, foreign_id, summary_id = old.id, new.id, foreign.id, summary.id
        db.commit()
    records = authenticated.get('/api/memory/records',
                                params={'project_id': project_id}).json()
    old_state = next(row['state_hash'] for row in records if row['id'] == old_id)
    url = f'/api/memory/records/{old_id}/supersede'
    assert authenticated.post(url, json={'replacement_id': new_id,
        'expected_state_hash': '0' * 64}, headers=h).status_code == 409
    assert authenticated.post(url, json={'replacement_id': foreign_id,
        'expected_state_hash': old_state}, headers=h).status_code == 409
    response = authenticated.post(url, json={'replacement_id': new_id,
        'expected_state_hash': old_state}, headers=h)
    assert response.status_code == 200, response.text
    assert response.json()['superseded_by_id'] == new_id
    assert authenticated.post(url, json={'replacement_id': new_id,
        'expected_state_hash': old_state}, headers=h).status_code == 409
    with session_factory()() as db:
        old_record = get_record(db, project_id=project_id, agent_id=agent_id,
                                record_id=old_id)[0]
        assert old_record.status == 'superseded'
        assert old_record.superseded_by_id == new_id
        hits = search_records(db, project_id=project_id, agent_id=agent_id,
                              query='retention days')
        assert [hit.record_id for hit in hits] == [new_id]
        context = build_context(db, project_id=project_id, agent_id=agent_id)
        assert f'record:{old_id}' not in context
        assert f'record:{new_id}' in context
        assert f'derived_summary:{summary_id}' not in context
