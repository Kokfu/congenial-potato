"""Exact immutable artifact retrieval with project and provenance checks."""
import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import ArtifactVersion, Execution, Task
from .services import authorize_agent_project
from .document_drafts import DocumentDraftError, fixture_for_run
from .document_draft_contract import render_document_fixture


class ArtifactIntegrityError(RuntimeError):
    pass


def read_version(db: Session, *, project_id: str, version_id: str,
                 agent_id: str | None = None) -> tuple[ArtifactVersion, bytes] | None:
    if agent_id is not None:
        authorize_agent_project(db, agent_id, project_id, 'project.execute')
    row = db.scalar(select(ArtifactVersion).where(
        ArtifactVersion.id == version_id,
        ArtifactVersion.project_id == project_id))
    if row is None:
        return None
    if row.version < 1 or (row.version == 1) != (row.parent_id is None):
        raise ArtifactIntegrityError('Artifact version chain is invalid')
    if row.parent_id is not None:
        parent = db.get(ArtifactVersion, row.parent_id)
        if (parent is None or parent.project_id != project_id or
            parent.artifact_id != row.artifact_id or parent.version + 1 != row.version):
            raise ArtifactIntegrityError('Artifact parent is invalid')
    if row.execution_id is not None:
        execution = db.get(Execution, row.execution_id)
        task = db.get(Task, execution.task_id) if execution else None
        if task is None or task.project_id != project_id or row.author != execution.agent_id:
            raise ArtifactIntegrityError('Artifact execution provenance is invalid')
    root = get_settings().artifact_dir.resolve()
    path = Path(row.storage_ref).resolve()
    if not path.is_relative_to(root) or path.parent != root / row.artifact_id or path.name != row.digest:
        raise ArtifactIntegrityError('Artifact storage path is outside the store')
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ArtifactIntegrityError('Artifact bytes unavailable') from exc
    if len(content) != row.size or hashlib.sha256(content).hexdigest() != row.digest:
        raise ArtifactIntegrityError('Artifact storage integrity failed')
    if row.execution_id is not None:
        try:
            document = fixture_for_run(db, execution, authority=False)
            if document and content != render_document_fixture(document).encode():
                raise DocumentDraftError('Saved draft differs from reviewed references')
        except DocumentDraftError as exc:
            raise ArtifactIntegrityError('Document draft provenance changed') from exc
    return row, content


def provenance(db: Session, row: ArtifactVersion) -> dict:
    execution = db.get(Execution, row.execution_id) if row.execution_id else None
    return {'id': row.id, 'artifact_id': row.artifact_id, 'project_id': row.project_id,
            'version': row.version, 'parent_id': row.parent_id,
            'execution_id': row.execution_id,
            'task_id': execution.task_id if execution else None,
            'author': row.author, 'digest': row.digest,
            'mime_type': row.mime_type, 'size': row.size,
            'created_at': row.created_at}
