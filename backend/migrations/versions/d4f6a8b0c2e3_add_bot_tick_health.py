"""add bot tick outcome log and per-bot failure state

Revision ID: d4f6a8b0c2e3
Revises: c3d5e7f9a1b2
Create Date: 2026-11-11 15:00:00.000000

Adds ``bot_tick_runs`` (one row per bot tick: counts, market state, or the error of a
crashed tick; pruned after a week) and three failure-state columns on ``bot_sessions``
(when and why processing last failed, and how many ticks in a row). Additive.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4f6a8b0c2e3'
down_revision: str | Sequence[str] | None = 'c3d5e7f9a1b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create bot_tick_runs and add the failure-state columns."""
    op.create_table(
        'bot_tick_runs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ran_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('market_open', sa.Boolean(), nullable=False),
        sa.Column('processed', sa.Integer(), nullable=False),
        sa.Column('skipped', sa.Integer(), nullable=False),
        sa.Column('failed', sa.Integer(), nullable=False),
        sa.Column('flattened', sa.Integer(), nullable=False),
        sa.Column('reconciled', sa.Integer(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_bot_tick_runs_ran_at', 'bot_tick_runs', ['ran_at'])
    op.add_column(
        'bot_sessions', sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column('bot_sessions', sa.Column('last_failure_error', sa.Text(), nullable=True))
    op.add_column(
        'bot_sessions',
        sa.Column('consecutive_failures', sa.Integer(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    """Drop the failure-state columns and bot_tick_runs."""
    op.drop_column('bot_sessions', 'consecutive_failures')
    op.drop_column('bot_sessions', 'last_failure_error')
    op.drop_column('bot_sessions', 'last_failure_at')
    op.drop_index('idx_bot_tick_runs_ran_at', table_name='bot_tick_runs')
    op.drop_table('bot_tick_runs')
