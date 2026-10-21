"""Preserve existing objectives as the first owner-reference brief revision."""
from hashlib import sha256
from alembic import op
import sqlalchemy as sa

revision = 'e6b8d130a9f2'
down_revision = 'd5a7c920e1f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('brief_revision', sa.Integer(),
                                      nullable=False, server_default='1'))
    op.alter_column('projects', 'brief_revision', server_default=None)
    table = op.create_table('project_brief_versions',
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), primary_key=True),
        sa.Column('revision', sa.Integer(), primary_key=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.Column('actor', sa.String(160), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('revision >= 1', name='ck_project_brief_revision'))
    bind = op.get_bind()
    # Stream rows rather than accumulating all source documents in migration memory.
    rows = bind.execute(sa.text('SELECT id, objective, created_at FROM projects')
                        .execution_options(stream_results=True)).mappings()
    for row in rows:
        bind.execute(table.insert().values(project_id=row['id'], revision=1,
            content=row['objective'], digest=sha256(row['objective'].encode('utf-8')).hexdigest(),
            actor='migration:existing-objective', created_at=row['created_at']))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text('SELECT 1 FROM project_brief_versions WHERE revision > 1 LIMIT 1')).first():
        raise RuntimeError('Cannot erase revised project brief history')
    op.drop_table('project_brief_versions')
    op.drop_column('projects', 'brief_revision')
