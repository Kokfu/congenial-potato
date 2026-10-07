"""Persist untrusted, sender-bound task communication without auto replies."""
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Agent, AuditEvent, Execution, Task, TaskMessage
from .services import authorize_agent_project

MAX_REPLY_DEPTH = 3
MAX_MESSAGES_PER_EXECUTION = 20
MAX_MESSAGES_PER_TASK = 100


class MessageInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sender_execution_id: str
    recipient_agent_id: str
    correlation_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,99}$')
    content: str = Field(min_length=1, max_length=10000)
    reply_to_id: str | None = None


class MessageError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def message_hash(data: MessageInput) -> str:
    return hashlib.sha256(json.dumps(data.model_dump(mode='json'),
                                     sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def send_message(db: Session, task_id: str, data: MessageInput,
                 owner_id: str) -> tuple[TaskMessage, bool]:
    hint = db.get(Execution, data.sender_execution_id)
    if hint is None:
        raise MessageError('source_missing')
    root = db.execute(select(Execution).where(Execution.id == hint.root_id)
                      .with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if root is None or root.cancelled:
        raise MessageError('source_cancelled')
    source = db.execute(select(Execution).where(Execution.id == hint.id)
                        .with_for_update().execution_options(populate_existing=True)).scalar_one()
    target_task = db.execute(select(Task).where(Task.id == task_id)
                             .with_for_update()).scalar_one_or_none()
    if target_task is None:
        raise MessageError('task_missing')
    source_task = db.get(Task, source.task_id)
    if source_task.project_id != target_task.project_id:
        raise MessageError('task_scope')
    digest = message_hash(data)
    existing = db.scalar(select(TaskMessage).where(
        TaskMessage.sender_execution_id == source.id,
        TaskMessage.correlation_key == data.correlation_key))
    if existing is not None:
        if existing.task_id != task_id or existing.payload_hash != digest:
            raise MessageError('correlation_reused')
        return existing, False
    if source.cancelled or source.status not in ('running', 'succeeded'):
        raise MessageError('source_unavailable')
    recipient = db.get(Agent, data.recipient_agent_id)
    if recipient is None or recipient.status != 'active':
        raise MessageError('recipient_unavailable')
    authorize_agent_project(db, source.agent_id, target_task.project_id, 'project.execute')
    authorize_agent_project(db, recipient.id, target_task.project_id, 'project.execute')
    reply_depth = 0
    if data.reply_to_id is not None:
        prior = db.get(TaskMessage, data.reply_to_id)
        if (prior is None or prior.task_id != task_id or
                prior.recipient_agent_id != source.agent_id or
                prior.sender_agent_id != recipient.id):
            raise MessageError('invalid_reply')
        reply_depth = prior.reply_depth + 1
        if reply_depth > MAX_REPLY_DEPTH:
            raise MessageError('reply_limit')
    execution_count = db.scalar(select(func.count(TaskMessage.id)).where(
        TaskMessage.sender_execution_id == source.id))
    task_count = db.scalar(select(func.count(TaskMessage.id)).where(
        TaskMessage.task_id == task_id))
    if execution_count >= MAX_MESSAGES_PER_EXECUTION or task_count >= MAX_MESSAGES_PER_TASK:
        raise MessageError('message_limit')
    message = TaskMessage(project_id=target_task.project_id, task_id=task_id,
                          sender_execution_id=source.id, sender_agent_id=source.agent_id,
                          recipient_agent_id=recipient.id, correlation_key=data.correlation_key,
                          payload_hash=digest, content=data.content,
                          reply_to_id=data.reply_to_id, reply_depth=reply_depth)
    db.add(message)
    db.flush()
    db.add(AuditEvent(actor=owner_id, action='task.message.send', resource=message.id,
                      outcome='recorded', detail={'sender_execution_id': source.id,
                                                  'recipient_agent_id': recipient.id,
                                                  'payload_hash': digest}))
    return message, True
