"""Add a commit-ordered project activity cursor.

Revision ID: a8c4d2e1f069
Revises: a72d4c0b13e5
"""
from alembic import op
import sqlalchemy as sa

revision = 'a8c4d2e1f069'
down_revision = 'a72d4c0b13e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('activity_seq', sa.Integer(),
                                        nullable=False, server_default='0'))
    op.create_table('project_activity',
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'),
                  primary_key=True),
        sa.Column('sequence', sa.Integer(), primary_key=True),
        sa.Column('actor', sa.String(160), nullable=False),
        sa.Column('action', sa.String(120), nullable=False),
        sa.Column('resource', sa.String(240), nullable=False),
        sa.Column('outcome', sa.String(30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('sequence >= 1', name='ck_project_activity_sequence'))


def downgrade() -> None:
    op.drop_table('project_activity')
    op.drop_column('projects', 'activity_seq')
