"""Persist untrusted runtime collaboration proposals.

Revision ID: e91b0267c3d4
Revises: d2b084f1ac95
"""
from alembic import op
import sqlalchemy as sa

revision = 'e91b0267c3d4'
down_revision = 'd2b084f1ac95'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('collaboration_proposals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source_execution_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('admitted_ref', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['source_execution_id'], ['executions.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_execution_id'))


def downgrade() -> None:
    op.drop_table('collaboration_proposals')
