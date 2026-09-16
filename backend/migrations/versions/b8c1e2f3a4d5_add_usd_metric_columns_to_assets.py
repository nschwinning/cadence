"""rename asset metric columns from EUR to USD

Revision ID: b8c1e2f3a4d5
Revises: d3f8b6a2c9e1
Create Date: 2026-09-16 09:00:00.000000

The asset universe is USD-normalized; rename the normalized metric columns to
match. Pure column renames — no data is transformed, so any pre-existing values
carry over under the new names until each asset is next re-derived.

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8c1e2f3a4d5'
down_revision: str | Sequence[str] | None = 'd3f8b6a2c9e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'assets', 'market_cap_eur', new_column_name='market_cap_usd'
    )
    op.alter_column(
        'assets', 'avg_daily_turnover_eur', new_column_name='avg_daily_turnover_usd'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'assets', 'avg_daily_turnover_usd', new_column_name='avg_daily_turnover_eur'
    )
    op.alter_column(
        'assets', 'market_cap_usd', new_column_name='market_cap_eur'
    )
