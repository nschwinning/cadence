"""add include_watchlist paper-trading session column

Revision ID: b2d4f6a8c0e2
Revises: a1c3e5f7b9d2
Create Date: 2026-10-20 12:00:00.000000

Per-session, build-time-frozen watchlist-inclusion opt-in (default off). When a
session has it enabled, each rebalance (and the opening allocation, which runs through
the rebalance flow) assembles its candidate universe from the union of universe- and
watchlist-membership assets instead of universe-membership assets only. Existing rows
backfill to false (opted out), so already-built sessions keep their universe-only
candidate universe unchanged.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c0e2'
down_revision: str | Sequence[str] | None = 'a1c3e5f7b9d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'paper_trading_sessions',
        sa.Column(
            'include_watchlist',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('paper_trading_sessions', 'include_watchlist')
