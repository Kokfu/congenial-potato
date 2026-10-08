"""Deterministic project and agent ceilings for canonical tool resources."""
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Agent, AgentProjectGrant, AuditEvent, PolicyRule, Project
from .services import AccessDenied, authorize_agent_project


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class PolicyDecision:
    effect: Literal['allow', 'deny', 'require_approval']
    snapshot: dict


def canonical_policy_resource(action: str, project_id: str,
                              resource_id: str | None) -> str:
    from .tool_gateway import DEFINITIONS
    if action not in DEFINITIONS:
        raise PolicyError('Tool action unavailable')
    try:
        project = str(UUID(project_id))
        resource = str(UUID(resource_id)) if resource_id else None
    except (ValueError, AttributeError) as exc:
        raise PolicyError('Invalid resource identifier') from exc
    prefix = f'project:{project}'
    if resource is None:
        return prefix
    if action == 'project.artifact.read':
        return f'{prefix}/artifact-version:{resource}'
    if action == 'project.artifact.write':
        return f'{prefix}/artifact:{resource}'
    raise PolicyError('Tool has no subresource scope')


def set_tool_policy(db: Session, *, project_id: str, agent_id: str | None,
                    action: str, resource_id: str | None,
                    effect: str, owner_id: str) -> PolicyRule:
    if effect not in ('allow', 'deny', 'require_approval'):
        raise PolicyError('Invalid policy effect')
    if db.get(Project, project_id) is None:
        raise PolicyError('Project unavailable')
    if agent_id is not None and db.get(Agent, agent_id) is None:
        raise PolicyError('Agent unavailable')
    resource = canonical_policy_resource(action, project_id, resource_id)
    subject = f'agent:{agent_id}' if agent_id else f'project:{project_id}'
    row = db.scalar(select(PolicyRule).where(
        PolicyRule.subject == subject, PolicyRule.action == action,
        PolicyRule.resource == resource).with_for_update())
    if row is None:
        row = PolicyRule(subject=subject, action=action,
                         resource=resource, effect=effect, revision=1)
        db.add(row)
        db.flush()
    else:
        row.effect = effect
        row.revision += 1
    db.add(AuditEvent(actor=owner_id, action='tool.policy.set', resource=row.id,
                      outcome='allowed', detail={'subject': subject, 'action': action,
                                                 'resource': resource, 'effect': effect,
                                                 'revision': row.revision}))
    return row


def evaluate_tool_policy(db: Session, *, agent_id: str, project_id: str,
                         action: str, resource: str) -> PolicyDecision:
    """Fail closed unless both project ceiling and agent rule admit the tool."""
    try:
        authorize_agent_project(db, agent_id, project_id, 'project.execute')
    except AccessDenied:
        return PolicyDecision('deny', {'reason': 'project_grant_denied'})
    try:
        prefix = canonical_policy_resource(action, project_id, None)
    except PolicyError:
        return PolicyDecision('deny', {'reason': 'unknown_tool_or_project'})
    if resource != prefix:
        segment = ('artifact-version:' if action == 'project.artifact.read' else
                   'artifact:' if action == 'project.artifact.write' else '')
        expected_start = prefix + '/' + segment
        if not segment or not resource.startswith(expected_start):
            return PolicyDecision('deny', {'reason': 'resource_scope_denied'})
        try:
            if canonical_policy_resource(action, project_id,
                                         resource[len(expected_start):]) != resource:
                return PolicyDecision('deny', {'reason': 'resource_scope_denied'})
        except PolicyError:
            return PolicyDecision('deny', {'reason': 'resource_scope_denied'})
    rows = db.scalars(select(PolicyRule).where(
        PolicyRule.subject.in_([f'project:{project_id}', f'agent:{agent_id}']),
        PolicyRule.action == action,
        PolicyRule.resource.in_([prefix, resource]))
        .order_by(PolicyRule.id).with_for_update()).all()
    project_rules = [row for row in rows if row.subject == f'project:{project_id}']
    agent_rules = [row for row in rows if row.subject == f'agent:{agent_id}']
    snapshot = {'rules': [{'id': row.id, 'revision': row.revision,
                           'effect': row.effect} for row in rows]}
    if any(row.effect == 'deny' for row in rows):
        return PolicyDecision('deny', snapshot)
    if not project_rules or not agent_rules:
        return PolicyDecision('deny', {**snapshot, 'reason': 'missing_ceiling_or_grant'})
    if any(row.effect not in ('allow', 'require_approval') for row in rows):
        return PolicyDecision('deny', {**snapshot, 'reason': 'unknown_policy_effect'})
    from .tool_gateway import DEFINITIONS
    if DEFINITIONS[action].approval_required or any(
            row.effect == 'require_approval' for row in rows):
        return PolicyDecision('require_approval', snapshot)
    return PolicyDecision('allow', snapshot)
