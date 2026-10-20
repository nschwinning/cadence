"""add use_fundamentals paper-trading session column

Revision ID: d7e2f9a4c1b3
Revises: f3a4b5c6d7e8
Create Date: 2026-10-18 09:00:00.000000

Per-session, build-time-frozen company-fundamentals opt-in (default off). When a
session has it enabled and is frozen on a fundamentals-aware rebalance prompt, its
rebalances attach a per-ticker company-fundamentals block to the agent's candidates
and holdings. Existing rows backfill to false (opted out), so already-built sessions
are byte-for-byte unchanged in what their rebalance agent receives.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7e2f9a4c1b3'
down_revision: str | Sequence[str] | None = 'f3a4b5c6d7e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'paper_trading_sessions',
        sa.Column(
            'use_fundamentals',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('paper_trading_sessions', 'use_fundamentals')
