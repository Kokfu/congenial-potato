"""Add owner-managed daily schedule definitions.

Revision ID: a62c3d9f0b14
Revises: f82a7c0d491e
"""
from alembic import op
import sqlalchemy as sa

revision = 'a62c3d9f0b14'
down_revision = 'f82a7c0d491e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('schedules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('title', sa.String(240), nullable=False),
        sa.Column('timezone', sa.String(100), nullable=False),
        sa.Column('local_hour', sa.Integer(), nullable=False),
        sa.Column('local_minute', sa.Integer(), nullable=False),
        sa.Column('root_cap', sa.Numeric(12, 6), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('local_hour BETWEEN 0 AND 23', name='ck_schedule_hour'),
        sa.CheckConstraint('local_minute BETWEEN 0 AND 59', name='ck_schedule_minute'),
        sa.CheckConstraint('root_cap > 0', name='ck_schedule_root_cap'),
        sa.CheckConstraint('revision >= 1', name='ck_schedule_revision'))
    op.create_index('ix_schedules_enabled', 'schedules', ['enabled', 'id'])


def downgrade() -> None:
    op.drop_index('ix_schedules_enabled', table_name='schedules')
    op.drop_table('schedules')
