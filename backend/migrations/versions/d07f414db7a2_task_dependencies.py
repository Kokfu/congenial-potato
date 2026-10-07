"""Add scoped task dependency edges.

Revision ID: d07f414db7a2
Revises: c391e5bc912a
"""
from alembic import op
import sqlalchemy as sa

revision = 'd07f414db7a2'
down_revision = 'c391e5bc912a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('task_dependencies',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('prerequisite_id', sa.String(length=36), nullable=False),
        sa.Column('dependent_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('prerequisite_id <> dependent_id', name='ck_task_dependency_distinct'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['prerequisite_id'], ['tasks.id']),
        sa.ForeignKeyConstraint(['dependent_id'], ['tasks.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('prerequisite_id', 'dependent_id'))
    op.create_index('ix_task_dependencies_dependent_id', 'task_dependencies', ['dependent_id'])


def downgrade() -> None:
    op.drop_index('ix_task_dependencies_dependent_id', table_name='task_dependencies')
    op.drop_table('task_dependencies')
