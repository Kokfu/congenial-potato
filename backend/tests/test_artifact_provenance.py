import hashlib
from uuid import uuid4

import pytest

from workforce.artifact_read import ArtifactIntegrityError, read_version
from workforce.config import get_settings
from workforce.db import session_factory
from workforce.memory import add_candidate, get_record
from workforce.memory_context import build_context
from workforce.memory_search import search_records
from workforce.models import (Agent, AgentConfigVersion, AgentProjectGrant,
                              ArtifactVersion, Execution, Project, Task)
from workforce.services import AccessDenied


def test_exact_versions_scope_digest_and_memory_source(authenticated):
    with session_factory()() as db:
        project, private = Project(name='Artifact project'), Project(name='Private')
        agent = Agent(name='Author', role='specialist')
        db.add_all([project, private, agent])
        db.flush()
        task = Task(project_id=project.id, title='Write synthetic artifact')
        config = AgentConfigVersion(agent_id=agent.id, version=1, instructions='Fixture',
                                    provider_connection='fixture', model_id='fake-v1')
        db.add_all([task, config, AgentProjectGrant(agent_id=agent.id,
            project_id=project.id, action='project.execute', allowed=True)])
        db.flush()
        execution = Execution(task_id=task.id, agent_id=agent.id,
                              config_version_id=config.id, root_id=str(uuid4()),
                              workflow_id=f'artifact-gate:{uuid4()}', status='succeeded')
        db.add(execution)
        db.flush()
        artifact_id = str(uuid4())
        rows = []
        for version, content in [(1, b'First synthetic version'),
                                 (2, b'Second synthetic version')]:
            digest = hashlib.sha256(content).hexdigest()
            path = get_settings().artifact_dir / artifact_id / digest
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            row = ArtifactVersion(artifact_id=artifact_id, project_id=project.id,
                                  version=version,
                                  parent_id=rows[-1].id if rows else None,
                                  execution_id=execution.id, author=agent.id,
                                  digest=digest, mime_type='text/markdown',
                                  size=len(content), storage_ref=str(path))
            db.add(row)
            db.flush()
            rows.append(row)
        claim = add_candidate(db, project_id=project.id, agent_id=agent.id,
                              kind='observation', subject_key='artifact-result',
                              content='Artifact version two records the result.',
                              trust_origin='model_inference',
                              sources=[('artifact_version', rows[1].id)])
        claim.status = 'active'
        ids = [row.id for row in rows]
        claim_id = claim.id
        project_id, private_id, agent_id = project.id, private.id, agent.id
        db.commit()
    # A fresh session simulates retrieval after process restart.
    with session_factory()() as db:
        first = read_version(db, project_id=project_id, agent_id=agent_id,
                             version_id=ids[0])
        second = read_version(db, project_id=project_id, agent_id=agent_id,
                              version_id=ids[1])
        assert first[1] == b'First synthetic version'
        assert second[1] == b'Second synthetic version'
        assert second[0].parent_id == first[0].id
        assert second[0].execution_id == execution.id
        found = get_record(db, project_id=project_id, agent_id=agent_id,
                           record_id=claim_id)
        assert [(source.source_kind, source.source_id) for source in found[1]] == [
            ('artifact_version', ids[1])]
        assert read_version(db, project_id=project_id, agent_id=agent_id,
                            version_id='unknown') is None
        with pytest.raises(AccessDenied):
            read_version(db, project_id=private_id, agent_id=agent_id,
                         version_id=ids[1])
        assert read_version(db, project_id=project_id, agent_id=agent_id,
                            version_id=ids[0])[1] != second[1]
        assert f'record:{claim_id}' in build_context(
            db, project_id=project_id, agent_id=agent_id)
        path = get_settings().artifact_dir / artifact_id / second[0].digest
        path.write_bytes(b'Corrupted bytes')
        with pytest.raises(ArtifactIntegrityError):
            read_version(db, project_id=project_id, agent_id=agent_id,
                         version_id=ids[1])
        with pytest.raises(ArtifactIntegrityError):
            build_context(db, project_id=project_id, agent_id=agent_id)
        with pytest.raises(ArtifactIntegrityError):
            search_records(db, project_id=project_id, agent_id=agent_id,
                           query='Artifact version')
        assert authenticated.get(f'/api/artifacts/versions/{ids[1]}').status_code == 503
        second[0].storage_ref = '/tmp/outside-artifact-store'
        db.flush()
        with pytest.raises(ArtifactIntegrityError):
            read_version(db, project_id=project_id, agent_id=agent_id,
                         version_id=ids[1])
