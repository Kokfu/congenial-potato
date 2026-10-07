"""Owner assignment records; authorization remains in the grant service."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Agent, Task, TaskAssignment
from .services import AccessDenied, authorize_agent_project


class AssignmentError(ValueError):
    pass


def assign_executor(db: Session, task: Task, agent_id: str,
                    owner_id: str) -> tuple[TaskAssignment, bool]:
    # Callers lock the task before entering here, serializing competing owners.
    if task.status != 'backlog':
        raise AssignmentError('Task is no longer in backlog')
    agent = db.get(Agent, agent_id)
    if agent is None or agent.status != 'active':
        raise AssignmentError('Agent is unavailable')
    authorize_agent_project(db, agent_id, task.project_id, 'project.execute')
    assignment = db.scalar(select(TaskAssignment).where(TaskAssignment.task_id == task.id))
    if assignment is not None:
        if assignment.agent_id != agent_id:
            raise AssignmentError('Task already has another executor')
        return assignment, False
    assignment = TaskAssignment(task_id=task.id, agent_id=agent_id,
                                assigned_by=owner_id)
    db.add(assignment)
    db.flush()
    task.revision += 1
    return assignment, True
