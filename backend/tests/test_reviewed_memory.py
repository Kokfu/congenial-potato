import json

from dbos import DBOS
from sqlalchemy import select

from workforce.db import session_factory
from workforce.memory import add_candidate
from workforce.memory_runtime import parse_memory_output
from workforce.models import MemoryConflict, MemoryRecord, Owner, Task
from workforce.worker import dispatch_once


def headers(client):
    return {'Origin': 'http://localhost:8080',
            'X-CSRF-Token': client.cookies['workforce_csrf']}


def source_fixture(authenticated, output):
    h = headers(authenticated)
    project = authenticated.post('/api/projects', json={'name': 'Memory project'}, headers=h).json()
    agent = authenticated.post('/api/agents', json={
        'name': 'Memory worker', 'role': 'specialist',
        'instructions': 'FIXTURE_MEMORY_JSON:' + output,
        'provider_connection': 'fixture-memory', 'model_id': 'memory-v1',
        'output_contract': 'memory.v1'}, headers=h).json()
    task = authenticated.post('/api/tasks', json={
        'project_id': project['id'], 'title': 'Synthetic research'}, headers=h).json()
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True},
        headers=h).status_code == 201
    dispatch = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={
        'agent_id': agent['id'], 'root_cap': '1.0'}, headers=h)
    assert dispatch.status_code == 202, dispatch.text
    execution_id = dispatch.json()['execution_id']
    DBOS(config={'name': 'workforce-test',
                 'system_database_url': 'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test',
                 'application_version': 'usage-normalization-v1'})
    DBOS.launch()
    try:
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'succeeded'
    finally:
        DBOS.destroy()
    return h, project, agent, task, execution_id


def test_runtime_candidate_requires_review_and_preserves_conflict(authenticated):
    output = json.dumps({'kind': 'decision', 'subject_key': 'retention-period',
                         'content': 'Keep synthetic records for 30 days',
                         'trust_origin': 'model_inference'})
    h, project, agent, task, execution_id = source_fixture(authenticated, output)
    candidates = authenticated.get('/api/memory-candidates',
                                   params={'project_id': project['id']}).json()
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate['sources'] == [{'kind': 'execution', 'id': execution_id}]
    assert candidate['existing_claims'] == []
    with session_factory()() as db:
        assert db.get(MemoryRecord, candidate['id']).status == 'candidate'
        assert db.get(MemoryRecord, candidate['id']).trust_origin == 'model_inference'
        owner_id = db.scalar(select(Owner.id))
        existing = add_candidate(db, project_id=project['id'], agent_id=agent['id'],
                                 kind='fact', subject_key='retention-period',
                                 content='Keep synthetic records for 90 days',
                                 trust_origin='external_claim', sources=[('task', task['id'])])
        existing.status = 'active'
        existing.reviewed_by_id = owner_id
        db.commit()
        existing_id = existing.id
    decision_url = f"/api/memory-candidates/{candidate['id']}/decision"
    assert authenticated.post(decision_url, json={
        'approved': True, 'payload_hash': candidate['payload_hash']}, headers=h).status_code == 409
    assert authenticated.post(decision_url, json={
        'approved': True, 'payload_hash': '0' * 64,
        'acknowledged_conflict_ids': [existing_id]}, headers=h).status_code == 409
    result = authenticated.post(decision_url, json={
        'approved': True, 'payload_hash': candidate['payload_hash'],
        'acknowledged_conflict_ids': [existing_id]}, headers=h)
    assert result.status_code == 200, result.text
    assert result.json()['trust_origin'] == 'approved_decision'
    with session_factory()() as db:
        assert db.get(MemoryRecord, existing_id).status == 'active'
        assert db.get(MemoryRecord, candidate['id']).status == 'active'
        assert db.scalar(select(MemoryConflict.other_record_id)) == existing_id


def test_rejected_output_and_mutated_candidate_have_no_promotion(authenticated):
    h, project, _, _, _ = source_fixture(authenticated,
        '{"kind":"fact","kind":"decision","subject_key":"bad",'
        '"content":"Bad","trust_origin":"model_inference"}')
    assert authenticated.get('/api/memory-candidates',
                             params={'project_id': project['id']}).json() == []
    with session_factory()() as db:
        assert db.scalars(select(MemoryRecord)).all() == []
    h2, project2, _, _, _ = source_fixture(authenticated, json.dumps({
        'kind': 'claim', 'subject_key': 'claim', 'content': 'Original',
        'trust_origin': 'external_claim'}))
    candidate = authenticated.get('/api/memory-candidates',
                                  params={'project_id': project2['id']}).json()[0]
    with session_factory()() as db:
        db.get(MemoryRecord, candidate['id']).content = 'Changed after proposal'
        db.commit()
    response = authenticated.post(f"/api/memory-candidates/{candidate['id']}/decision",
                                  json={'approved': True, 'payload_hash': candidate['payload_hash']},
                                  headers=h2)
    assert response.status_code == 409
    with session_factory()() as db:
        assert db.get(MemoryRecord, candidate['id']).status == 'candidate'


def test_parser_rejects_extra_fields():
    try:
        parse_memory_output('{"kind":"claim","subject_key":"x","content":"x",'
                            '"trust_origin":"model_inference","grant":true}')
    except ValueError:
        pass
    else:
        raise AssertionError('Extra authority field accepted')


def test_review_rechecks_revoked_grant_and_cancellation(authenticated):
    output = json.dumps({'kind': 'claim', 'subject_key': 'claim',
                         'content': 'Synthetic claim', 'trust_origin': 'external_claim'})
    h, project, agent, _, execution_id = source_fixture(authenticated, output)
    candidate = authenticated.get('/api/memory-candidates',
                                  params={'project_id': project['id']}).json()[0]
    url = f"/api/memory-candidates/{candidate['id']}/decision"
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': False},
        headers=h).status_code == 201
    assert authenticated.post(url, json={'approved': True,
        'payload_hash': candidate['payload_hash']}, headers=h).status_code == 403
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True},
        headers=h).status_code == 201
    assert authenticated.post(f'/api/executions/{execution_id}/cancel',
                              headers=h).status_code == 200
    assert authenticated.post(url, json={'approved': True,
        'payload_hash': candidate['payload_hash']}, headers=h).status_code == 409
    with session_factory()() as db:
        assert db.get(MemoryRecord, candidate['id']).status == 'invalidated'
