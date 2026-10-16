import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from dbos import DBOS
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import ArtifactVersion, Execution, ToolInvocation
from workforce.tool_gateway import ToolProposalError, parse_tool_output, record_tool_output
from workforce.worker import dispatch_once
from workforce.tool_effects import apply_admitted_tools


def headers(client):
    return {'Origin': 'http://localhost:8080',
            'X-CSRF-Token': client.cookies['workforce_csrf']}


def fixture_run(authenticated, output, with_policy=True, web_grant=False):
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
    if with_policy:
        for action in ('project.memory.search', 'project.artifact.read',
                       'project.artifact.write',
                       *(['project.web.read'] if web_grant else [])):
            for agent_id in (None, agent['id']):
                assert authenticated.post('/api/tool-policies', json={
                    'project_id': project['id'], 'agent_id': agent_id,
                    'action': action,
                    'effect': ('require_approval' if with_policy == 'approval' and
                               action == 'project.artifact.write' and agent_id is None
                               else 'allow')}, headers=h).status_code == 201
    if web_grant:
        response = authenticated.post('/api/read-destination-grants', json={
            'project_id': project['id'], 'agent_id': agent['id'],
            'host': 'example.test', 'enabled': True,
            'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
            headers=h)
        assert response.status_code == 201, response.text
    response = authenticated.post(f"/api/tasks/{task['id']}/dispatch", json={
        'agent_id': agent['id'], 'root_cap': '1.0'}, headers=h)
    assert response.status_code == 202, response.text
    execution_id = response.json()['execution_id']
    DBOS(config={'name': 'workforce-test',
                 'system_database_url': os.environ.get('DBOS_SYSTEM_DATABASE_URL',
                     'postgresql://postgres:phase1fixture@127.0.0.1:55433/workforce_dbos_test'),
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
    assert row['effect'] == 'write' and row['status'] == 'awaiting_approval'
    assert row['policy_decision'] == 'require_approval'
    assert row['approval']['status'] == 'pending'
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


def test_valid_proposal_stays_denied_without_policy(authenticated):
    output = json.dumps({'version': 1, 'action': 'project.memory.search',
                         'arguments': {'project_id': 'PROJECT_ID', 'query': 'retention'}})
    project, _, _ = fixture_run(authenticated, output, with_policy=False)
    row = authenticated.get('/api/tool-invocations',
                            params={'project_id': project['id']}).json()[0]
    assert row['status'] == 'denied'
    assert row['policy_decision'] == 'deny'


def test_project_approval_ceiling_suspends_write(authenticated):
    output = json.dumps({'version': 1, 'action': 'project.artifact.write',
                         'arguments': {'project_id': 'PROJECT_ID',
                                       'artifact_id': str(uuid4()),
                                       'content': 'Approval fixture',
                                       'expected_parent': None}})
    project, _, _ = fixture_run(authenticated, output, with_policy='approval')
    row = authenticated.get('/api/tool-invocations',
                            params={'project_id': project['id']}).json()[0]
    assert row['policy_decision'] == 'require_approval'
    assert row['status'] == 'awaiting_approval'
    with session_factory()() as db:
        assert db.scalar(select(ArtifactVersion.id)) is None


def test_web_read_proposal_is_typed_scoped_and_never_executed(authenticated):
    output = json.dumps({'version': 1, 'action': 'project.web.read',
                         'arguments': {'project_id': 'PROJECT_ID',
                                       'url': 'https://example.test/source',
                                       'max_bytes': 1024, 'timeout_seconds': 2}})
    project, _, execution_id = fixture_run(authenticated, output, web_grant=True)
    row = authenticated.get('/api/tool-invocations',
                            params={'project_id': project['id']}).json()[0]
    assert row['execution_id'] == execution_id
    assert row['resource'] == f"project:{project['id']}/web-origin:example.test"
    assert row['policy_decision'] == 'require_approval'
    assert row['status'] == 'proposed' and row['approval'] is None
    with session_factory()() as db:
        assert db.get(ToolInvocation, row['id']).status == 'proposed'
    staged = authenticated.post(
        f"/api/tool-invocations/{row['id']}/stage-web-read-approval",
        headers=headers(authenticated))
    assert staged.status_code == 200, staged.text
    assert staged.json()['target_version'] is not None
    approved = authenticated.post(f"/api/tool-invocations/{row['id']}/decision",
        json={'approved': True, 'payload_hash': staged.json()['payload_hash']},
        headers=headers(authenticated))
    assert approved.status_code == 200, approved.text
    assert approved.json()['status'] == 'approved_staged'
    assert apply_admitted_tools() == 0
    assert authenticated.post(f'/api/executions/{execution_id}/cancel',
                              headers=headers(authenticated)).status_code == 200
    assert authenticated.get('/api/tool-invocations',
                             params={'project_id': project['id']}).json()[0]['status'] == 'invalidated'


def test_web_read_proposal_without_exact_grant_stays_denied(authenticated):
    output = json.dumps({'version': 1, 'action': 'project.web.read',
                         'arguments': {'project_id': 'PROJECT_ID',
                                       'url': 'https://example.test/source'}})
    project, _, _ = fixture_run(authenticated, output, with_policy=False)
    row = authenticated.get('/api/tool-invocations',
                            params={'project_id': project['id']}).json()[0]
    assert row['status'] == 'denied'
    for url in ('https://user@example.test/source',
                'http://example.test/source', 'https://example.test:0/source'):
        with pytest.raises(ToolProposalError):
            parse_tool_output(json.dumps({'version': 1,
                'action': 'project.web.read', 'arguments': {
                    'project_id': project['id'], 'url': url}}))


def test_web_read_approval_rechecks_destination_revision(authenticated):
    output = json.dumps({'version': 1, 'action': 'project.web.read',
                         'arguments': {'project_id': 'PROJECT_ID',
                                       'url': 'https://example.test/source'}})
    project, _, execution_id = fixture_run(authenticated, output, web_grant=True)
    row = authenticated.get('/api/tool-invocations',
                            params={'project_id': project['id']}).json()[0]
    with session_factory()() as db:
        agent_id = db.get(Execution, execution_id).agent_id
    changed = authenticated.post('/api/read-destination-grants', json={
        'project_id': project['id'], 'agent_id': agent_id,
        'host': 'example.test', 'enabled': False,
        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
        headers=headers(authenticated))
    assert changed.status_code == 201
    rejected = authenticated.post(
        f"/api/tool-invocations/{row['id']}/stage-web-read-approval",
        headers=headers(authenticated))
    assert rejected.status_code == 409
    assert authenticated.get('/api/tool-invocations',
        params={'project_id': project['id']}).json()[0]['status'] == 'invalidated'


def test_staged_web_read_approval_invalidates_after_grant_change(authenticated):
    output = json.dumps({'version': 1, 'action': 'project.web.read',
                         'arguments': {'project_id': 'PROJECT_ID',
                                       'url': 'https://example.test/source'}})
    project, _, execution_id = fixture_run(authenticated, output, web_grant=True)
    row = authenticated.get('/api/tool-invocations',
                            params={'project_id': project['id']}).json()[0]
    staged = authenticated.post(
        f"/api/tool-invocations/{row['id']}/stage-web-read-approval",
        headers=headers(authenticated))
    assert staged.status_code == 200
    with session_factory()() as db:
        agent_id = db.get(Execution, execution_id).agent_id
    assert authenticated.post('/api/read-destination-grants', json={
        'project_id': project['id'], 'agent_id': agent_id,
        'host': 'example.test', 'enabled': True,
        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()},
        headers=headers(authenticated)).status_code == 201
    invalid = authenticated.post(f"/api/tool-invocations/{row['id']}/decision",
        json={'approved': True, 'payload_hash': staged.json()['payload_hash']},
        headers=headers(authenticated))
    assert invalid.status_code == 409
    current = authenticated.get('/api/tool-invocations',
                                params={'project_id': project['id']}).json()[0]
    assert current['status'] == 'invalidated'
    assert current['approval']['status'] == 'invalidated'
    assert apply_admitted_tools() == 0
