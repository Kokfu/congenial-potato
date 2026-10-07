"""Record normalized provider response metadata.

Revision ID: b289c6e2c9bf
Revises: a1d387ca2e90
"""
from alembic import op
import sqlalchemy as sa

revision = 'b289c6e2c9bf'
down_revision = 'a1d387ca2e90'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('model_calls', sa.Column('provider_request_id', sa.String(length=240), nullable=True))
    op.add_column('model_calls', sa.Column('usage', sa.JSON(), nullable=True))
    op.execute("UPDATE model_calls SET usage = '{}'::json WHERE usage IS NULL")
    op.alter_column('model_calls', 'usage', nullable=False)


def downgrade() -> None:
    op.drop_column('model_calls', 'usage')
    op.drop_column('model_calls', 'provider_request_id')
