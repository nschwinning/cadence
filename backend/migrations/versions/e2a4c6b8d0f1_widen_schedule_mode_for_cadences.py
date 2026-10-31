"""widen paper_trading_sessions.schedule_mode for weekly/monthly cadences

Revision ID: e2a4c6b8d0f1
Revises: c4e6a8b0d2f4
Create Date: 2026-10-23 12:00:00.000000

The ``schedule_mode`` column was created as a non-native enum over MANUAL /
SCHEDULED / DAILY_REBALANCING, which SQLAlchemy sized as VARCHAR(17) — the length
of the longest value then (``DAILY_REBALANCING``). The weekly/monthly rebalance
cadences add ``WEEKLY_REBALANCING`` (18) and ``MONTHLY_REBALANCING`` (19), which
do not fit, so this widens the column to VARCHAR(32). No data is rewritten and
existing values are unaffected; the downgrade narrows it back to VARCHAR(17)
(safe only while no weekly/monthly rows exist).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2a4c6b8d0f1'
down_revision: str | Sequence[str] | None = 'c4e6a8b0d2f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'paper_trading_sessions',
        'schedule_mode',
        existing_type=sa.String(length=17),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default='SCHEDULED',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'paper_trading_sessions',
        'schedule_mode',
        existing_type=sa.String(length=32),
        type_=sa.String(length=17),
        existing_nullable=False,
        existing_server_default='SCHEDULED',
    )
