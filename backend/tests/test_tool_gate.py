from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select

from workforce.config import get_settings
from workforce.db import session_factory
from workforce.models import (Approval, ArtifactVersion, AuditEvent, Execution,
                              SyntheticToolEffect, ToolInvocation)
from workforce.tool_effects import apply_admitted_tools

from test_tool_approval import decide, proposed_write
from test_tool_gateway import fixture_run


def test_concurrent_fake_write_is_one_effect_with_full_provenance(authenticated):
    project, execution_id, _, row = proposed_write(authenticated)
    assert decide(authenticated, row).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: apply_admitted_tools(), range(2)))
    assert sorted(outcomes) == [0, 1]
    with session_factory()() as db:
        invocation = db.get(ToolInvocation, row['id'])
        approval = db.get(Approval, row['approval']['id'])
        execution = db.get(Execution, execution_id)
        effect = db.get(SyntheticToolEffect, row['id'])
        audit = db.scalar(select(AuditEvent).where(
            AuditEvent.effect_key == f"tool-effect:{row['id']}"))
        assert invocation.execution_id == execution.id
        assert invocation.project_id == project['id']
        assert approval.tool_invocation_id == invocation.id
        assert approval.decision_payload_hash == approval.payload_hash
        assert effect.argument_hash == invocation.argument_hash
        assert effect.project_id == project['id']
        assert audit is not None and audit.resource == invocation.id
        assert invocation.status == 'succeeded'
        assert len(db.scalars(select(SyntheticToolEffect)).all()) == 1
        assert db.scalar(select(ArtifactVersion.id)) is None


def test_authorized_artifact_read_uses_validated_version(authenticated):
    version_id, artifact_id = str(uuid4()), str(uuid4())
    output = json.dumps({'version': 1, 'action': 'project.artifact.read',
                         'arguments': {'project_id': 'PROJECT_ID',
                                       'version_id': version_id}})
    project, _, _ = fixture_run(authenticated, output)
    row = authenticated.get('/api/tool-invocations',
                            params={'project_id': project['id']}).json()[0]
    assert row['status'] == 'admitted' and row['policy_decision'] == 'allow'
    content = b'Synthetic readable artifact'
    digest = hashlib.sha256(content).hexdigest()
    path = get_settings().artifact_dir / artifact_id / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    with session_factory()() as db:
        db.add(ArtifactVersion(id=version_id, artifact_id=artifact_id,
            project_id=project['id'], version=1, parent_id=None,
            execution_id=None, author='owner', digest=digest,
            mime_type='text/markdown', size=len(content), storage_ref=str(path)))
        db.commit()
    assert apply_admitted_tools() == 1
    with session_factory()() as db:
        effect = db.get(SyntheticToolEffect, row['id'])
        assert effect.result == {'version_id': version_id, 'digest': digest,
                                 'size': len(content)}
