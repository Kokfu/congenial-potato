"""Local fake tool effects with a separate, idempotent effect ledger."""
from collections.abc import Callable
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from .artifact_read import ArtifactIntegrityError, read_version
from .db import session_factory
from .memory_search import search_records
from .models import (Approval, AuditEvent, BudgetAccount, Execution,
                     SyntheticToolEffect, ToolInvocation)
from .tool_approval import _invalid_reason, invocation_invalid_reason


def _fake_result(db: Session, invocation: ToolInvocation,
                 agent_id: str) -> dict:
    args = invocation.arguments
    if invocation.action == 'project.memory.search':
        hits = search_records(db, project_id=invocation.project_id,
                              agent_id=agent_id, query=args['query'], limit=20)
        return {'record_ids': [hit.record_id for hit in hits]}
    if invocation.action == 'project.artifact.read':
        found = read_version(db, project_id=invocation.project_id,
                             version_id=args['version_id'], agent_id=agent_id)
        if found is None or len(found[1]) > 65536:
            raise ValueError('Artifact version unavailable or too large')
        row, _ = found
        return {'version_id': row.id, 'digest': row.digest, 'size': row.size}
    if invocation.action == 'project.artifact.write':
        content = args['content'].encode()
        return {'artifact_id': args['artifact_id'],
                'digest': hashlib.sha256(content).hexdigest(),
                'size': len(content), 'simulated': True}
    raise ValueError('Tool action unavailable')


def _finish_from_ledger(db: Session, invocation: ToolInvocation,
                        effect: SyntheticToolEffect) -> None:
    if (effect.project_id != invocation.project_id or
        effect.action != invocation.action or
        effect.argument_hash != invocation.argument_hash):
        invocation.status = 'unknown'
        outcome = 'unknown'
    else:
        invocation.status = 'succeeded'
        outcome = 'reconciled'
    db.add(AuditEvent(actor='worker', action='tool.apply',
                      resource=invocation.id, outcome=outcome,
                      effect_key=f'tool-effect:{invocation.id}',
                      detail={'ledger_key': effect.invocation_key}))


def apply_admitted_tools(after_ledger_commit: Callable[[], None] | None = None) -> int:
    """Recheck before each effect; an existing ledger row is reconciliation."""
    with session_factory()() as db:
        ids = db.scalars(select(ToolInvocation.id).where(
            ToolInvocation.status == 'admitted')
            .order_by(ToolInvocation.created_at, ToolInvocation.id)
            .limit(20)).all()
    completed = 0
    for invocation_id in ids:
        with session_factory()() as db:
            hint = db.get(ToolInvocation, invocation_id)
            if hint is None:
                continue
            source = db.get(Execution, hint.execution_id)
            if source is None:
                continue
            db.execute(select(Execution).where(Execution.id == source.root_id)
                       .with_for_update()).scalar_one_or_none()
            invocation = db.execute(select(ToolInvocation).where(
                ToolInvocation.id == invocation_id).with_for_update()
                .execution_options(populate_existing=True)).scalar_one()
            if invocation.status != 'admitted':
                continue
            existing = db.get(SyntheticToolEffect, invocation.id)
            if existing is not None:
                _finish_from_ledger(db, invocation, existing)
                db.commit()
                completed += 1
                continue
            approval = db.scalar(select(Approval).where(
                Approval.tool_invocation_id == invocation.id).with_for_update())
            if invocation.policy_decision == 'require_approval':
                if (approval is None or approval.status != 'approved' or
                    approval.decision_payload_hash != approval.payload_hash):
                    reason = 'approval_unavailable'
                else:
                    reason = _invalid_reason(db, invocation, approval, source)
            elif invocation.policy_decision == 'allow' and approval is None:
                reason = invocation_invalid_reason(db, invocation, source,
                                                   expected_policy='allow')
            else:
                reason = 'policy_or_approval_changed'
            if reason is None and db.get(BudgetAccount, source.root_id) is None:
                reason = 'root_budget_unavailable'
            if reason is not None:
                invocation.status = 'invalidated'
                if approval and approval.status == 'approved':
                    approval.status = 'invalidated'
                db.add(AuditEvent(actor='worker', action='tool.apply',
                                  resource=invocation.id, outcome='denied',
                                  detail={'reason': reason}))
                db.commit()
                continue
            try:
                result = _fake_result(db, invocation, source.agent_id)
            except (ArtifactIntegrityError, ValueError) as exc:
                invocation.status = 'failed'
                db.add(AuditEvent(actor='worker', action='tool.apply',
                                  resource=invocation.id, outcome='failed',
                                  detail={'reason': type(exc).__name__}))
                db.commit()
                continue
            # This intentionally commits the synthetic effect independently of
            # the invocation checkpoint, modelling an external success window.
            with session_factory()() as ledger_db:
                ledger_db.add(SyntheticToolEffect(
                    invocation_key=invocation.id, project_id=invocation.project_id,
                    action=invocation.action, argument_hash=invocation.argument_hash,
                    result=result))
                ledger_db.commit()
            if after_ledger_commit is not None:
                after_ledger_commit()
            effect = db.get(SyntheticToolEffect, invocation.id)
            _finish_from_ledger(db, invocation, effect)
            db.commit()
            completed += 1
    return completed
