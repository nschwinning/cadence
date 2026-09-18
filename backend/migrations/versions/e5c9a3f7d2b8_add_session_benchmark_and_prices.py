"""add per-session benchmark and the benchmark_prices series

Revision ID: e5c9a3f7d2b8
Revises: d4b7e2f9a1c6
Create Date: 2026-09-18 12:00:00.000000

Two additions for benchmarking a paper-trading session against a market index:

1. A new ``benchmark_prices`` table storing the system-owned daily closing price
   per catalog benchmark (unique per benchmark+date, indexed on the same pair).
   A scheduled cron job fills it; comparisons are derived on read from it.
2. A non-nullable ``benchmark`` column on ``paper_trading_sessions`` naming the
   benchmark a session is compared against. Added in three steps (add nullable,
   backfill existing rows to the default ``SP500``, set NOT NULL) so existing
   sessions default to the S&P 500.

The benchmark enum values are embedded as literals (no import from app code,
which may drift), matching the non-native ``Enum`` columns used elsewhere.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5c9a3f7d2b8'
down_revision: str | Sequence[str] | None = 'd4b7e2f9a1c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Catalog benchmark ids, in enum-declaration order.
_BENCHMARK_VALUES = (
    "SP500",
    "DJIA",
    "NYSE_COMPOSITE",
    "NASDAQ_COMPOSITE",
    "NASDAQ_100",
    "RUSSELL_2000",
    "SP100",
    "WILSHIRE_5000",
)


def upgrade() -> None:
    # --- 1. benchmark_prices table ---
    op.create_table(
        "benchmark_prices",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "benchmark",
            sa.Enum(*_BENCHMARK_VALUES, name="benchmark", native_enum=False),
            nullable=False,
        ),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "benchmark", "price_date", name="uq_benchmark_prices_benchmark_date"
        ),
    )
    op.create_index(
        "idx_benchmark_prices_benchmark_date",
        "benchmark_prices",
        ["benchmark", "price_date"],
        unique=False,
    )

    # --- 2. session benchmark column (non-nullable, added in three steps) ---
    op.add_column(
        "paper_trading_sessions",
        sa.Column(
            "benchmark",
            sa.Enum(*_BENCHMARK_VALUES, name="benchmark", native_enum=False),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE paper_trading_sessions SET benchmark = 'SP500' "
        "WHERE benchmark IS NULL"
    )
    op.alter_column(
        "paper_trading_sessions",
        "benchmark",
        existing_type=sa.Enum(
            *_BENCHMARK_VALUES, name="benchmark", native_enum=False
        ),
        nullable=False,
        server_default="SP500",
    )


def downgrade() -> None:
    op.drop_column("paper_trading_sessions", "benchmark")
    op.drop_index(
        "idx_benchmark_prices_benchmark_date", table_name="benchmark_prices"
    )
    op.drop_table("benchmark_prices")
