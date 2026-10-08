"""Isolate activity sequencing from project domain row locks.

Revision ID: a9e3f40c2d16
Revises: a8c4d2e1f069
"""
from alembic import op
import sqlalchemy as sa

revision = 'a9e3f40c2d16'
down_revision = 'a8c4d2e1f069'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('project_activity_cursors',
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'),
                  primary_key=True),
        sa.Column('sequence', sa.Integer(), nullable=False))
    op.execute('INSERT INTO project_activity_cursors (project_id, sequence) '
               'SELECT id, activity_seq FROM projects')
    op.drop_column('projects', 'activity_seq')


def downgrade() -> None:
    op.add_column('projects', sa.Column('activity_seq', sa.Integer(),
                                        nullable=False, server_default='0'))
    op.execute('UPDATE projects SET activity_seq = c.sequence '
               'FROM project_activity_cursors c WHERE c.project_id = projects.id')
    op.drop_table('project_activity_cursors')
