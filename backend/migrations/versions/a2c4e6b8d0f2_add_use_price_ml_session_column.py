"""add use_price_ml paper-trading session column

Revision ID: a2c4e6b8d0f2
Revises: f7b3d9e1a2c4
Create Date: 2026-11-01 09:05:00.000000

Per-session, build-time-frozen price-ML opt-in (default off). When a session has
it enabled and is frozen on a price-ML-aware rebalance prompt, its rebalances
attach a per-ticker price-ML advisory block to the agent's candidates and
holdings. Existing rows backfill to false (opted out), so already-built sessions
are byte-for-byte unchanged in what their rebalance agent receives.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2c4e6b8d0f2'
down_revision: str | Sequence[str] | None = 'f7b3d9e1a2c4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'paper_trading_sessions',
        sa.Column(
            'use_price_ml',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('paper_trading_sessions', 'use_price_ml')
