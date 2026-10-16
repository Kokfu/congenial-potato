import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import Approval, ArtifactVersion, ToolInvocation, now

from test_tool_gateway import fixture_run, headers


def proposed_write(authenticated, *, artifact_id=None):
    artifact_id = artifact_id or str(uuid4())
    output = json.dumps({'version': 1, 'action': 'project.artifact.write',
                         'arguments': {'project_id': 'PROJECT_ID',
                                       'artifact_id': artifact_id,
                                       'content': 'Exact synthetic payload',
                                       'expected_parent': None}})
    project, _, execution_id = fixture_run(authenticated, output,
                                           with_policy='approval')
    row = authenticated.get('/api/tool-invocations',
                            params={'project_id': project['id']}).json()[0]
    assert row['status'] == 'awaiting_approval'
    assert row['approval']['status'] == 'pending'
    assert row['approval']['target_version'] is None
    return project, execution_id, artifact_id, row


def decide(client, row, approved=True, payload_hash=None):
    return client.post(f"/api/tool-invocations/{row['id']}/decision",
                       json={'approved': approved,
                             'payload_hash': payload_hash or row['approval']['payload_hash']},
                       headers=headers(client))


def test_exact_owner_approval_persists_without_effect(authenticated):
    _, _, _, row = proposed_write(authenticated)
    assert authenticated.get('/api/approvals').json() == []  # Artifact review stays separate.
    assert decide(authenticated, row, payload_hash='0' * 64).status_code == 409
    approved = decide(authenticated, row)
    assert approved.status_code == 200, approved.text
    assert approved.json()['status'] == 'admitted'
    assert approved.json()['approval_status'] == 'approved'
    assert decide(authenticated, row).status_code == 200
    with session_factory()() as db:
        approval = db.get(Approval, row['approval']['id'])
        assert approval.decision_payload_hash == row['approval']['payload_hash']
        assert db.scalar(select(ArtifactVersion.id)) is None


def test_owner_can_reject_pending_tool(authenticated):
    _, _, _, row = proposed_write(authenticated)
    rejected = decide(authenticated, row, approved=False)
    assert rejected.status_code == 200
    assert rejected.json()['status'] == 'rejected'
    assert decide(authenticated, row, approved=True).status_code == 409


@pytest.mark.parametrize('mutation', ['arguments', 'schema', 'policy', 'target', 'expiry'])
def test_changed_tool_approval_is_invalidated(authenticated, mutation):
    project, _, artifact_id, row = proposed_write(authenticated)
    with session_factory()() as db:
        invocation = db.get(ToolInvocation, row['id'])
        approval = db.get(Approval, row['approval']['id'])
        if mutation == 'arguments':
            invocation.arguments = {**invocation.arguments, 'content': 'Changed'}
        elif mutation == 'schema':
            approval.schema_hash = '0' * 64
        elif mutation == 'target':
            db.add(ArtifactVersion(artifact_id=artifact_id,
                project_id=project['id'], version=1, parent_id=None,
                execution_id=None, author='owner', digest='0' * 64,
                mime_type='text/markdown', size=1, storage_ref='/tmp/synthetic'))
        elif mutation == 'expiry':
            approval.expires_at = now() - timedelta(seconds=1)
        db.commit()
    if mutation == 'policy':
        response = authenticated.post('/api/tool-policies', json={
            'project_id': project['id'], 'action': 'project.artifact.write',
            'effect': 'deny'}, headers=headers(authenticated))
        assert response.status_code == 201
    response = decide(authenticated, row)
    assert response.status_code == 409
    with session_factory()() as db:
        assert db.get(ToolInvocation, row['id']).status == 'invalidated'
        assert db.get(Approval, row['approval']['id']).status in ('invalidated', 'expired')
        versions = db.scalars(select(ArtifactVersion)).all()
        assert len(versions) == (1 if mutation == 'target' else 0)


def test_cancellation_invalidates_pending_tool_approval(authenticated):
    _, execution_id, _, row = proposed_write(authenticated)
    assert authenticated.post(f'/api/executions/{execution_id}/cancel',
                              headers=headers(authenticated)).status_code == 200
    assert decide(authenticated, row).status_code == 409
    with session_factory()() as db:
        assert db.get(ToolInvocation, row['id']).status == 'invalidated'
        assert db.get(Approval, row['approval']['id']).status == 'invalidated'
