"""add use_news_sentiment paper-trading session column

Revision ID: c5e8f1a2b3d4
Revises: b3d5f7a9c1e3
Create Date: 2026-11-01 10:05:00.000000

Per-session, build-time-frozen news-sentiment opt-in (default off). When a session
has it enabled and is frozen on a sentiment-aware rebalance prompt, its rebalances
attach a per-ticker recency-weighted news-tone block to the agent's candidates and
holdings. Existing rows backfill to false (opted out), so already-built sessions are
byte-for-byte unchanged in what their rebalance agent receives.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c5e8f1a2b3d4'
down_revision: str | Sequence[str] | None = 'b3d5f7a9c1e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'paper_trading_sessions',
        sa.Column(
            'use_news_sentiment',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('paper_trading_sessions', 'use_news_sentiment')
