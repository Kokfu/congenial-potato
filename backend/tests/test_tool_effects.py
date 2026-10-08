import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.artifacts import apply_approved_artifacts
from workforce.models import (ArtifactVersion, AuditEvent, SyntheticToolEffect,
                              ToolInvocation)
from workforce.tool_effects import apply_admitted_tools

from test_tool_approval import decide, proposed_write
from test_tool_gateway import fixture_run, headers


def test_approved_fake_write_is_one_logical_effect(authenticated):
    project, _, artifact_id, row = proposed_write(authenticated)
    assert decide(authenticated, row).status_code == 200
    assert apply_approved_artifacts() == 0
    assert apply_admitted_tools() == 1
    assert apply_admitted_tools() == 0
    with session_factory()() as db:
        effect = db.scalar(select(SyntheticToolEffect))
        assert effect.invocation_key == row['id']
        assert effect.result['artifact_id'] == artifact_id
        assert effect.result['simulated'] is True
        assert db.get(ToolInvocation, row['id']).status == 'succeeded'
        assert db.scalar(select(ArtifactVersion.id)) is None
        assert len(db.scalars(select(AuditEvent).where(
            AuditEvent.effect_key == f"tool-effect:{row['id']}")).all()) == 1
    listing = authenticated.get('/api/tool-invocations',
                                params={'project_id': project['id']}).json()[0]
    assert listing['result']['simulated'] is True


def test_crash_after_fake_effect_reconciles_without_second_effect(authenticated):
    _, _, _, row = proposed_write(authenticated)
    assert decide(authenticated, row).status_code == 200
    with pytest.raises(RuntimeError, match='checkpoint lost'):
        apply_admitted_tools(after_ledger_commit=lambda: (_ for _ in ()).throw(
            RuntimeError('checkpoint lost')))
    with session_factory()() as db:
        assert db.get(ToolInvocation, row['id']).status == 'admitted'
        assert len(db.scalars(select(SyntheticToolEffect)).all()) == 1
    assert apply_admitted_tools() == 1
    with session_factory()() as db:
        assert db.get(ToolInvocation, row['id']).status == 'succeeded'
        assert len(db.scalars(select(SyntheticToolEffect)).all()) == 1
        assert db.scalar(select(AuditEvent).where(
            AuditEvent.effect_key == f"tool-effect:{row['id']}")).outcome == 'reconciled'


@pytest.mark.parametrize('change', ['policy', 'arguments', 'cancel'])
def test_recheck_blocks_subsequent_effect(authenticated, change):
    project, execution_id, _, row = proposed_write(authenticated)
    assert decide(authenticated, row).status_code == 200
    if change == 'policy':
        response = authenticated.post('/api/tool-policies', json={
            'project_id': project['id'], 'action': 'project.artifact.write',
            'effect': 'deny'}, headers=headers(authenticated))
        assert response.status_code == 201
    elif change == 'arguments':
        with session_factory()() as db:
            invocation = db.get(ToolInvocation, row['id'])
            invocation.arguments = {**invocation.arguments, 'content': 'Changed'}
            db.commit()
    else:
        assert authenticated.post(f'/api/executions/{execution_id}/cancel',
                                  headers=headers(authenticated)).status_code == 200
    assert apply_admitted_tools() == 0
    with session_factory()() as db:
        assert db.scalar(select(SyntheticToolEffect)) is None
        assert db.get(ToolInvocation, row['id']).status == 'invalidated'


def test_allowed_memory_search_is_bounded_fake_read(authenticated):
    output = json.dumps({'version': 1, 'action': 'project.memory.search',
                         'arguments': {'project_id': 'PROJECT_ID', 'query': 'retention'}})
    project, _, _ = fixture_run(authenticated, output)
    row = authenticated.get('/api/tool-invocations',
                            params={'project_id': project['id']}).json()[0]
    assert row['status'] == 'admitted' and row['approval'] is None
    assert apply_admitted_tools() == 1
    with session_factory()() as db:
        effect = db.get(SyntheticToolEffect, row['id'])
        assert effect.result == {'record_ids': []}
        assert db.get(ToolInvocation, row['id']).status == 'succeeded'


def test_mismatched_existing_ledger_is_unknown_and_never_retried(authenticated):
    _, _, _, row = proposed_write(authenticated)
    assert decide(authenticated, row).status_code == 200
    with session_factory()() as db:
        db.add(SyntheticToolEffect(invocation_key=row['id'],
            project_id=row['arguments']['project_id'],
            action='project.artifact.write', argument_hash='0' * 64,
            result={'simulated': True}))
        db.commit()
    assert apply_admitted_tools() == 1
    with session_factory()() as db:
        assert db.get(ToolInvocation, row['id']).status == 'unknown'
        assert len(db.scalars(select(SyntheticToolEffect)).all()) == 1
