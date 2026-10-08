"""Persist immutable synthetic tool proposals before policy admission.

Revision ID: f52a183b64d0
Revises: f42d97ea61c0
"""
from alembic import op
import sqlalchemy as sa

revision = 'f52a183b64d0'
down_revision = 'f42d97ea61c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('tool_invocations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('execution_id', sa.String(36), sa.ForeignKey('executions.id'),
                  nullable=False, unique=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('action', sa.String(120), nullable=False),
        sa.Column('definition_version', sa.Integer(), nullable=False),
        sa.Column('schema_hash', sa.String(64), nullable=False),
        sa.Column('argument_hash', sa.String(64), nullable=False),
        sa.Column('arguments', sa.JSON(), nullable=False),
        sa.Column('resource', sa.String(240), nullable=False),
        sa.Column('effect', sa.String(30), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table('tool_invocations')
