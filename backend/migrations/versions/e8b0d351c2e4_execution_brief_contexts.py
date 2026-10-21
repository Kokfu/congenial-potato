"""Record prepared fixture source messages without inferring provider delivery."""
from alembic import op
import sqlalchemy as sa

revision = 'e8b0d351c2e4'
down_revision = 'e7a9c240b1d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('execution_brief_contexts',
        sa.Column('execution_id', sa.String(36), sa.ForeignKey('execution_brief_sources.execution_id'), primary_key=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('char_length(message) <= 6000', name='ck_brief_context_size'))


def downgrade() -> None:
    if op.get_bind().execute(sa.text('SELECT 1 FROM execution_brief_contexts LIMIT 1')).first():
        raise RuntimeError('Cannot erase prepared brief context history')
    op.drop_table('execution_brief_contexts')
