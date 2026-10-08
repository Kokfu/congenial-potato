"""Constrain project tool policy and record proposal decisions.

Revision ID: f62a9d017c3b
Revises: f52a183b64d0
"""
from alembic import op
import sqlalchemy as sa

revision = 'f62a9d017c3b'
down_revision = 'f52a183b64d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint('uq_policy_subject_action_resource',
                                'policy_rules', ['subject', 'action', 'resource'])
    op.create_check_constraint('ck_policy_effect', 'policy_rules',
        "effect IN ('allow', 'deny', 'require_approval')")
    op.create_check_constraint('ck_policy_revision', 'policy_rules',
        'revision >= 1')
    op.add_column('tool_invocations', sa.Column('policy_decision', sa.String(30),
                                                nullable=False, server_default='deny'))
    op.add_column('tool_invocations', sa.Column('policy_snapshot', sa.JSON(),
                                                nullable=False, server_default='{}'))


def downgrade() -> None:
    op.drop_column('tool_invocations', 'policy_snapshot')
    op.drop_column('tool_invocations', 'policy_decision')
    op.drop_constraint('ck_policy_revision', 'policy_rules', type_='check')
    op.drop_constraint('ck_policy_effect', 'policy_rules', type_='check')
    op.drop_constraint('uq_policy_subject_action_resource', 'policy_rules', type_='unique')
