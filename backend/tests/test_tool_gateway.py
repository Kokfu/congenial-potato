import json
from uuid import uuid4

import pytest
from dbos import DBOS
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import ArtifactVersion, Execution, ToolInvocation
from workforce.tool_gateway import ToolProposalError, parse_tool_output, record_tool_output
from workforce.worker import dispatch_once


def headers(client):
    return {'Origin': 'http://localhost:8080',
            'X-CSRF-Token': client.cookies['workforce_csrf']}


def fixture_run(authenticated, output):
    h = headers(authenticated)
    project = authenticated.post('/api/projects', json={'name': 'Tool project'},
                                 headers=h).json()
    other = authenticated.post('/api/projects', json={'name': 'Other project'},
                               headers=h).json()
    agent = authenticated.post('/api/agents', json={
        'name': 'Tool proposer', 'role': 'specialist',
        'instructions': 'FIXTURE_TOOL_JSON:' + output.replace('PROJECT_ID', project['id'])
                                               .replace('OTHER_ID', other['id']),
        'provider_connection': 'fixture-tool', 'model_id': 'tool-v1',
        'output_contract': 'tool.v1'}, headers=h).json()
    task = authenticated.post('/api/tasks', json={
        'project_id': project['id'], 'title': 'Synthetic tool proposal'}, headers=h).json()
    assert authenticated.post(f"/api/agents/{agent['id']}/grants", json={
        'project_id': project['id'], 'action': 'project.execute', 'allowed': True},
        headers=h).status_code == 201
    response = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={
        'agent_id': agent['id'], 'root_cap': '1.0'}, headers=h)
    assert response.status_code == 202, response.text
    execution_id = response.json()['execution_id']
    DBOS(config={'name': 'workforce-test',
                 'system_database_url': 'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test',
                 'application_version': 'usage-normalization-v1'})
    DBOS.launch()
    try:
        assert dispatch_once() == 1
        assert DBOS.retrieve_workflow(f'execution:{execution_id}').get_result() == 'succeeded'
    finally:
        DBOS.destroy()
    return project, other, execution_id


def test_worker_proposes_canonical_tool_without_effect(authenticated):
    artifact_id = str(uuid4())
    output = json.dumps({'version': 1, 'action': 'project.artifact.write',
                         'arguments': {'project_id': 'PROJECT_ID',
                                       'artifact_id': artifact_id,
                                       'content': 'Synthetic proposal',
                                       'expected_parent': None}})
    project, _, execution_id = fixture_run(authenticated, output)
    rows = authenticated.get('/api/tool-invocations',
                             params={'project_id': project['id']}).json()
    assert len(rows) == 1
    row = rows[0]
    assert row['execution_id'] == execution_id
    assert row['resource'] == f"project:{project['id']}/artifact:{artifact_id}"
    assert row['effect'] == 'write' and row['status'] == 'proposed'
    assert len(row['schema_hash']) == len(row['argument_hash']) == 64
    with session_factory()() as db:
        assert db.scalar(select(ArtifactVersion.id)) is None
        assert len(db.scalars(select(ToolInvocation)).all()) == 1
        assert record_tool_output(db, db.get(Execution, execution_id),
                                  output.replace('PROJECT_ID', project['id'])) is None
        assert len(db.scalars(select(ToolInvocation)).all()) == 1
    assert authenticated.post(f'/api/executions/{execution_id}/cancel',
                              headers=headers(authenticated)).status_code == 200
    assert authenticated.get('/api/tool-invocations',
                             params={'project_id': project['id']}).json()[0]['status'] == 'invalidated'


@pytest.mark.parametrize('output', [
    '{"version":1,"action":"project.memory.search","arguments":{"project_id":"OTHER_ID","query":"x"}}',
    '{"version":1,"action":"project.artifact.write","arguments":{"project_id":"PROJECT_ID","artifact_id":"bad","content":"x"}}',
    '{"version":1,"action":"project.memory.search","arguments":{"project_id":"PROJECT_ID","query":"x","grant":true}}',
    '{"version":1,"action":"host.shell","arguments":{"project_id":"PROJECT_ID"}}',
])
def test_invalid_or_cross_project_proposal_has_no_invocation(authenticated, output):
    project, _, _ = fixture_run(authenticated, output)
    assert authenticated.get('/api/tool-invocations',
                             params={'project_id': project['id']}).json() == []
    with session_factory()() as db:
        assert db.scalar(select(ArtifactVersion.id)) is None


def test_duplicate_keys_and_wrong_version_rejected():
    project = str(uuid4())
    for content in [
        '{"version":1,"action":"project.memory.search","action":"host.shell",'
        f'"arguments":{{"project_id":"{project}","query":"x"}}}}',
        json.dumps({'version': 2, 'action': 'project.memory.search',
                    'arguments': {'project_id': project, 'query': 'x'}}),
    ]:
        with pytest.raises(ToolProposalError):
            parse_tool_output(content)
