"""Exact, synthetic artifact proposals and idempotent local effects."""
import hashlib
import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path
from collections.abc import Callable
from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy import select

from .config import get_settings
from .models import Approval, ArtifactVersion, AuditEvent, Execution, ModelCall, Project, Task, now
from .services import AccessDenied, authorize_agent_project

SCHEMA_HASH = hashlib.sha256(b'fixture-artifact-v1:artifact_id,project_id,content,mime_type,expected_parent').hexdigest()
PAYLOAD_KEYS = {'artifact_id', 'project_id', 'content', 'mime_type', 'expected_parent'}


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def propose_fixture_artifact(db, execution: Execution, result: str) -> Approval:
    task = db.get(Task, execution.task_id)
    artifact_id = str(uuid5(NAMESPACE_URL, f'workforce-fixture:{execution.id}'))
    payload = {'artifact_id': artifact_id, 'project_id': task.project_id, 'content': result,
               'mime_type': 'text/markdown', 'expected_parent': None}
    approval = Approval(execution_id=execution.id, invocation_key=f'artifact:{execution.id}:1',
                        payload=payload, payload_hash=payload_hash(payload), schema_hash=SCHEMA_HASH,
                        resource=artifact_id, target_version=None, status='pending',
                        expires_at=now() + timedelta(days=1))
    db.add(approval)
    db.add(AuditEvent(actor=execution.agent_id, action='artifact.propose', resource=artifact_id,
                      outcome='pending', detail={'execution_id': execution.id, 'payload_hash': approval.payload_hash}))
    return approval


def proposal_valid(db, approval: Approval) -> bool:
    payload = approval.payload
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS:
        return False
    if not all(isinstance(payload[key], str) for key in ('artifact_id', 'project_id', 'content', 'mime_type')):
        return False
    if payload['mime_type'] != 'text/markdown' or not payload['content'] or len(payload['content'].encode()) > 65536:
        return False
    if payload['expected_parent'] is not None and not isinstance(payload['expected_parent'], str):
        return False
    try:
        UUID(payload['artifact_id'])
    except (ValueError, AttributeError):
        return False
    if approval.payload_hash != payload_hash(payload) or approval.schema_hash != SCHEMA_HASH:
        return False
    if approval.status == 'approved' and approval.decision_payload_hash != approval.payload_hash:
        return False
    if approval.resource != payload['artifact_id'] or approval.target_version != payload['expected_parent']:
        return False
    execution = db.execute(select(Execution).where(Execution.id == approval.execution_id).with_for_update()).scalar_one_or_none()
    if execution is None or execution.cancelled or execution.status != 'succeeded':
        return False
    task = db.get(Task, execution.task_id)
    if task.project_id != payload['project_id']:
        return False
    if db.scalar(select(ModelCall.id).where(ModelCall.execution_id == execution.id)) is None:
        return False
    try:
        authorize_agent_project(db, execution.agent_id, task.project_id, 'project.execute')
    except AccessDenied:
        return False
    if approval.expires_at <= now():
        return False
    return True


def apply_approved_artifacts(after_file_write: Callable[[], None] | None = None) -> int:
    """Worker-owned effect. A leftover content-addressed file is safe to retry."""
    from .db import session_factory
    applied = 0
    with session_factory()() as db:
        rows = db.scalars(select(Approval).where(
            Approval.status == 'approved', Approval.tool_invocation_id.is_(None))
                          .order_by(Approval.id).with_for_update(skip_locked=True).limit(20)).all()
        for approval in rows:
            if not proposal_valid(db, approval):
                approval.status = 'invalidated'
                db.add(AuditEvent(actor='worker', action='artifact.apply', resource=approval.resource,
                                  outcome='denied', detail={'approval_id': approval.id}))
                db.commit()
                continue
            payload = approval.payload
            # Serializes version assignment and precondition checks for this project.
            db.execute(select(Project).where(Project.id == payload['project_id']).with_for_update()).scalar_one()
            head = db.scalar(select(ArtifactVersion).where(ArtifactVersion.artifact_id == payload['artifact_id'])
                             .order_by(ArtifactVersion.version.desc()).limit(1))
            if (head.id if head else None) != payload['expected_parent']:
                approval.status = 'invalidated'
                db.add(AuditEvent(actor='worker', action='artifact.apply', resource=approval.resource,
                                  outcome='stale', detail={'approval_id': approval.id}))
                db.commit()
                continue
            content = payload['content'].encode()
            digest = hashlib.sha256(content).hexdigest()
            path = get_settings().artifact_dir / payload['artifact_id'] / digest
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                fd, temp = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
                try:
                    with os.fdopen(fd, 'wb') as handle:
                        handle.write(content)
                        handle.flush()
                        os.fsync(handle.fileno())
                    try:
                        os.link(temp, path)
                    except FileExistsError:
                        pass
                    directory_fd = os.open(path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                finally:
                    os.unlink(temp)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError('Artifact storage digest mismatch')
            if after_file_write is not None:
                after_file_write()
            db.add(ArtifactVersion(artifact_id=payload['artifact_id'], project_id=payload['project_id'],
                                   version=(head.version + 1 if head else 1), parent_id=(head.id if head else None),
                                   execution_id=approval.execution_id, author=db.get(Execution, approval.execution_id).agent_id,
                                   digest=digest, mime_type=payload['mime_type'], size=len(content), storage_ref=str(path)))
            approval.status = 'applied'
            db.add(AuditEvent(actor='worker', action='artifact.apply', resource=approval.resource,
                              outcome='allowed', effect_key=approval.invocation_key,
                              detail={'approval_id': approval.id, 'digest': digest}))
            db.commit()
            applied += 1
    return applied
