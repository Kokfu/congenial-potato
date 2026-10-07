"""Deterministic, project-scoped prerequisite graph admission."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Project, Task, TaskDependency


class TaskGraphError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def add_dependency(db: Session, dependent_id: str,
                   prerequisite_id: str) -> tuple[TaskDependency, bool]:
    dependent = db.get(Task, dependent_id)
    if dependent is None:
        raise TaskGraphError('task_missing')
    # Every graph mutation locks its project first. Dispatch locks the task;
    # the following task lock ensures an edge cannot land after dispatch.
    db.execute(select(Project).where(Project.id == dependent.project_id).with_for_update()).scalar_one()
    dependent = db.execute(select(Task).where(Task.id == dependent_id).with_for_update()).scalar_one()
    prerequisite = db.get(Task, prerequisite_id)
    if prerequisite is None or prerequisite.project_id != dependent.project_id:
        raise TaskGraphError('prerequisite_missing')
    if prerequisite_id == dependent_id:
        raise TaskGraphError('cycle')
    if dependent.status not in ('backlog', 'ready'):
        raise TaskGraphError('task_already_admitted')
    existing = db.scalar(select(TaskDependency).where(
        TaskDependency.prerequisite_id == prerequisite_id,
        TaskDependency.dependent_id == dependent_id))
    if existing is not None:
        return existing, False
    edges = db.scalars(select(TaskDependency).where(
        TaskDependency.project_id == dependent.project_id)).all()
    successors: dict[str, set[str]] = {}
    for edge in edges:
        successors.setdefault(edge.prerequisite_id, set()).add(edge.dependent_id)
    # Adding prerequisite -> dependent is cyclic iff dependent already reaches prerequisite.
    stack = [dependent_id]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current == prerequisite_id:
            raise TaskGraphError('cycle')
        if current not in seen:
            seen.add(current)
            stack.extend(successors.get(current, ()))
    edge = TaskDependency(project_id=dependent.project_id,
                          prerequisite_id=prerequisite_id, dependent_id=dependent_id)
    db.add(edge)
    db.flush()
    return edge, True


def dependencies_satisfied(db: Session, task_id: str) -> bool:
    statuses = db.scalars(select(Task.status).join(TaskDependency,
        Task.id == TaskDependency.prerequisite_id).where(
        TaskDependency.dependent_id == task_id)).all()
    return all(status == 'completed' for status in statuses)
