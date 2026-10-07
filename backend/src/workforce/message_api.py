"""Owner-controlled synthetic agent message commands and reads."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import db_session
from .messages import MessageError, MessageInput, send_message
from .models import OwnerSession, Task, TaskMessage
from .security import current_session, require_csrf
from .services import AccessDenied

router = APIRouter()


@router.get('/api/tasks/{task_id}/messages')
def list_messages(task_id: str, _: OwnerSession = Depends(current_session),
                  db: Session = Depends(db_session)):
    if db.get(Task, task_id) is None:
        raise HTTPException(404, 'Task not found')
    rows = db.scalars(select(TaskMessage).where(TaskMessage.task_id == task_id)
                      .order_by(TaskMessage.created_at, TaskMessage.id)).all()
    return [{'id': row.id, 'sender_execution_id': row.sender_execution_id,
             'sender_agent_id': row.sender_agent_id,
             'recipient_agent_id': row.recipient_agent_id, 'reply_to_id': row.reply_to_id,
             'reply_depth': row.reply_depth, 'content': row.content,
             'trust_origin': 'agent_message', 'created_at': row.created_at} for row in rows]


@router.post('/api/tasks/{task_id}/messages', status_code=201)
def create_message(task_id: str, data: MessageInput, response: Response,
                   session: OwnerSession = Depends(require_csrf),
                   db: Session = Depends(db_session)):
    try:
        message, created = send_message(db, task_id, data, session.owner_id)
    except AccessDenied as exc:
        raise HTTPException(403, 'Project access denied') from exc
    except MessageError as exc:
        raise HTTPException(404 if exc.code in ('task_missing', 'source_missing') else 409,
                            exc.code) from exc
    if not created:
        response.status_code = 200
    db.commit()
    return {'id': message.id, 'task_id': task_id,
            'sender_execution_id': message.sender_execution_id,
            'reply_depth': message.reply_depth}
