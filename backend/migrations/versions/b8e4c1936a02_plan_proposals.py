"""Add bounded plan proposals and project work keys.

Revision ID: b8e4c1936a02
Revises: e3a9c2704f1b
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8e4c1936a02'
down_revision = 'e3a9c2704f1b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('plan_revision', sa.Integer(),
                                       server_default='1', nullable=False))
    op.add_column('tasks', sa.Column('work_key', sa.String(length=100), nullable=True))
    op.create_unique_constraint('uq_task_project_work_key', 'tasks', ['project_id', 'work_key'])
    op.create_table('plan_proposals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('source_execution_id', sa.String(length=36), nullable=False),
        sa.Column('submitted_by', sa.String(length=36), nullable=False),
        sa.Column('proposal_key', sa.String(length=100), nullable=False),
        sa.Column('expected_revision', sa.Integer(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['source_execution_id'], ['executions.id']),
        sa.ForeignKeyConstraint(['submitted_by'], ['owners.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_execution_id', 'proposal_key', name='uq_plan_source_key'))


def downgrade() -> None:
    op.drop_table('plan_proposals')
    op.drop_constraint('uq_task_project_work_key', 'tasks', type_='unique')
    op.drop_column('tasks', 'work_key')
    op.drop_column('projects', 'plan_revision')
