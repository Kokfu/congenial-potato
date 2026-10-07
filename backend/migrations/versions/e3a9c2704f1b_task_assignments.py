"""Record the one executor assigned to each task.

Revision ID: e3a9c2704f1b
Revises: d07f414db7a2
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3a9c2704f1b'
down_revision = 'd07f414db7a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('task_assignments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('agent_id', sa.String(length=36), nullable=False),
        sa.Column('assigned_by', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id']),
        sa.ForeignKeyConstraint(['assigned_by'], ['owners.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id', name='uq_task_assignment_task'))


def downgrade() -> None:
    op.drop_table('task_assignments')
