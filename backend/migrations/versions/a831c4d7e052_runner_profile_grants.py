"""Persist inert owner-pinned runner profile grants.

Revision ID: a831c4d7e052
Revises: f1b5d24e7a93
"""
from alembic import op
import sqlalchemy as sa

revision = 'a831c4d7e052'
down_revision = 'f1b5d24e7a93'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('runner_profile_grants',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('profile_id', sa.String(120), nullable=False),
        sa.Column('profile_revision', sa.Integer(), nullable=False),
        sa.Column('profile_sha256', sa.String(64), nullable=False),
        sa.Column('image_id', sa.String(71), nullable=False),
        sa.Column('job_sha256', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('project_id', 'agent_id', 'profile_id', name='uq_runner_profile_scope'),
        sa.CheckConstraint('revision >= 1', name='ck_runner_profile_revision'),
        sa.CheckConstraint('profile_revision >= 1', name='ck_runner_profile_version'))


def downgrade() -> None:
    op.drop_table('runner_profile_grants')
