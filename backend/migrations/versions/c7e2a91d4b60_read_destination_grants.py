"""Persist exact project, agent and HTTPS host read grants.

Revision ID: c7e2a91d4b60
Revises: b0d7e32a4c19
"""
from alembic import op
import sqlalchemy as sa

revision = 'c7e2a91d4b60'
down_revision = 'b0d7e32a4c19'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('read_destination_grants',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('host', sa.String(253), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('project_id', 'agent_id', 'host', name='uq_read_destination_scope'),
        sa.CheckConstraint('revision >= 1', name='ck_read_destination_revision'))


def downgrade() -> None:
    op.drop_table('read_destination_grants')
