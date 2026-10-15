"""Typed tool proposal boundary. No proposal executes an effect."""
from dataclasses import dataclass
import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent, Execution, Task, ToolInvocation
from .services import AccessDenied, authorize_agent_project
from .tool_policy import evaluate_tool_policy
from .tool_approval import create_tool_approval
from .activity import record_activity
from .network_policy import canonical_public_url
from .local_read_experiment import ReadDenied
from .read_grants import active_read_grant_record
from .reviewed_runner_contract import PROFILE, RunnerInput
from .runner_grants import (RunnerGrantDenied, current_runner_grant_record,
                            runner_grant_snapshot, runner_scope_snapshot)


class MemorySearchArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: UUID
    query: str = Field(min_length=1, max_length=200)


class ArtifactReadArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: UUID
    version_id: UUID


class ArtifactWriteArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: UUID
    artifact_id: UUID
    content: str = Field(min_length=1, max_length=65536)
    expected_parent: UUID | None = None


class WebReadArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: UUID
    url: str = Field(min_length=1, max_length=2048)
    max_bytes: int = Field(default=65536, ge=1, le=65536)
    timeout_seconds: float = Field(default=3, gt=0, le=5)


class RunnerDigestArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: UUID
    input: RunnerInput


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1]
    action: str
    arguments: dict


@dataclass(frozen=True)
class ToolDefinition:
    action: str
    version: int
    input_model: type[BaseModel]
    effect: Literal['read', 'write']
    approval_required: bool = False

    @property
    def schema_hash(self) -> str:
        value = {'action': self.action, 'version': self.version,
                 'effect': self.effect, 'approval_required': self.approval_required,
                 'schema': self.input_model.model_json_schema()}
        return hashlib.sha256(json.dumps(value, sort_keys=True,
                                         separators=(',', ':')).encode()).hexdigest()


DEFINITIONS = {definition.action: definition for definition in (
    ToolDefinition('project.memory.search', 1, MemorySearchArgs, 'read'),
    ToolDefinition('project.artifact.read', 1, ArtifactReadArgs, 'read'),
    ToolDefinition('project.artifact.write', 1, ArtifactWriteArgs, 'write', True),
    ToolDefinition('project.web.read', 1, WebReadArgs, 'read', True),
    ToolDefinition('project.runner.digest', 1, RunnerDigestArgs, 'write', True),
)}


class ToolProposalError(ValueError):
    pass


def _distinct_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ToolProposalError('Duplicate JSON key')
        result[key] = value
    return result


def parse_tool_output(content: str) -> tuple[ToolDefinition, dict, str, str]:
    if len(content.encode('utf-8')) > 70000:
        raise ToolProposalError('Tool proposal too large')
    try:
        raw = json.loads(content, object_pairs_hook=_distinct_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid constant')))
        output = ToolOutput.model_validate(raw)
        definition = DEFINITIONS.get(output.action)
        if definition is None:
            raise ToolProposalError('Tool unavailable')
        args = definition.input_model.model_validate(output.arguments).model_dump(mode='json')
        if definition.action == 'project.artifact.write' and len(args['content'].encode()) > 65536:
            raise ToolProposalError('Tool content too large')
        project_id = args['project_id']
        if definition.action == 'project.memory.search':
            resource = f'project:{project_id}'
        elif definition.action == 'project.artifact.read':
            resource = f"project:{project_id}/artifact-version:{args['version_id']}"
        elif definition.action == 'project.artifact.write':
            resource = f"project:{project_id}/artifact:{args['artifact_id']}"
        elif definition.action == 'project.runner.digest':
            resource = f'project:{project_id}/runner-profile:{PROFILE.profile_id}'
        else:
            host, _ = canonical_public_url(args['url'])
            if len(host) > 180:
                raise ToolProposalError('Destination hostname exceeds policy resource limit')
            resource = f'project:{project_id}/web-origin:{host}'
        argument_hash = hashlib.sha256(json.dumps(args, sort_keys=True,
                                                  separators=(',', ':')).encode()).hexdigest()
        return definition, args, resource, argument_hash
    except (ValueError, TypeError, ValidationError, ReadDenied) as exc:
        raise ToolProposalError('Invalid tool proposal') from exc


def record_tool_output(db: Session, execution: Execution,
                       content: str) -> ToolInvocation | None:
    if db.scalar(select(ToolInvocation.id).where(
        ToolInvocation.execution_id == execution.id)) is not None:
        return None
    task = db.get(Task, execution.task_id)
    try:
        definition, args, resource, argument_hash = parse_tool_output(content)
        if task is None or args['project_id'] != task.project_id:
            raise AccessDenied('Tool project unavailable')
        authorize_agent_project(db, execution.agent_id, task.project_id, 'project.execute')
    except (ToolProposalError, AccessDenied) as exc:
        db.add(AuditEvent(actor=execution.agent_id, action='tool.parse',
                          resource=execution.id, outcome='denied',
                          detail={'reason': str(exc)},
                          effect_key=f'tool.parse:{execution.id}'))
        if task is not None:
            record_activity(db, project_id=task.project_id,
                            actor=execution.agent_id, action='tool.parse',
                            resource=execution.id, outcome='denied')
        return None
    decision = evaluate_tool_policy(db, agent_id=execution.agent_id,
                                    project_id=task.project_id,
                                    action=definition.action, resource=resource)
    snapshot = decision.snapshot
    if definition.action == 'project.web.read' and decision.effect != 'deny':
        try:
            host, _ = canonical_public_url(args['url'])
            grant = active_read_grant_record(db, project_id=task.project_id,
                agent_id=execution.agent_id, host=host)
            snapshot = {**snapshot, 'destination_grant': {
                'id': grant.id, 'revision': grant.revision}}
        except ReadDenied:
            snapshot = {**snapshot, 'reason': 'destination_grant_unavailable'}
            decision = type(decision)('deny', snapshot)
    if definition.action == 'project.runner.digest' and decision.effect != 'deny':
        try:
            grant = current_runner_grant_record(db, project_id=task.project_id,
                                               agent_id=execution.agent_id)
            snapshot = {**snapshot, 'runner_grant': runner_grant_snapshot(grant),
                        'runner_scope': runner_scope_snapshot(execution)}
        except RunnerGrantDenied:
            snapshot = {**snapshot, 'reason': 'runner_grant_unavailable'}
            decision = type(decision)('deny', snapshot)
    status = ({'deny': 'denied', 'allow': 'admitted',
               'require_approval': 'awaiting_approval'}[decision.effect]
              if definition.action not in ('project.web.read', 'project.runner.digest') else
              ('denied' if decision.effect == 'deny' else 'proposed'))
    row = ToolInvocation(execution_id=execution.id, project_id=task.project_id,
                         action=definition.action, definition_version=definition.version,
                         schema_hash=definition.schema_hash, argument_hash=argument_hash,
                         arguments=args, resource=resource, effect=definition.effect,
                         policy_decision=decision.effect,
                         policy_snapshot=snapshot, status=status)
    db.add(row)
    db.flush()
    if row.status == 'awaiting_approval':
        create_tool_approval(db, row)
    db.add(AuditEvent(actor=execution.agent_id, action='tool.propose',
                      resource=row.id, outcome=status,
                      detail={'action': row.action, 'resource': resource,
                              'schema_hash': row.schema_hash,
                              'argument_hash': row.argument_hash,
                              'policy_snapshot': row.policy_snapshot}))
    record_activity(db, project_id=task.project_id, actor=execution.agent_id,
                    action='tool.propose', resource=row.id, outcome=status)
    return row
