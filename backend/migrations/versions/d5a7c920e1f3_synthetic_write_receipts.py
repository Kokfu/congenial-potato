"""Persist one exact authenticated synthetic write receipt per admission."""
from alembic import op
import sqlalchemy as sa

revision = 'd5a7c920e1f3'
down_revision = 'c4e6a819d0b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('synthetic_write_receipts',
        sa.Column('invocation_id', sa.String(36),
            sa.ForeignKey('synthetic_write_admissions.invocation_id'), primary_key=True),
        sa.Column('receipt_sha256', sa.String(64), nullable=False),
        sa.Column('receipt', sa.JSON(), nullable=False),
        sa.Column('trust_origin', sa.String(30), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("trust_origin = 'synthetic_write'",
            name='ck_synthetic_write_receipt_trust'))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text('SELECT 1 FROM synthetic_write_receipts LIMIT 1')).first():
        raise RuntimeError('Cannot erase accepted synthetic write receipt history')
    op.drop_table('synthetic_write_receipts')
