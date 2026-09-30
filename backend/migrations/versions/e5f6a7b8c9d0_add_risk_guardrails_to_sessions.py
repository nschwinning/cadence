"""add portfolio risk-guardrail opt-in to sessions

Revision ID: e5f6a7b8c9d0
Revises: b3c4d5e6f7a8
Create Date: 2026-09-30 10:00:00.000000

Adds the opt-in deterministic portfolio risk guardrails, frozen at build time:

- ``paper_trading_sessions.risk_guardrails_enabled`` — per-session opt-in. Non-nullable
  with a ``false`` server default and backfilled to ``false`` for existing rows, so
  already-built sessions behave as guardrails off.
- ``paper_trading_sessions.max_asset_class_pct`` — frozen maximum fraction per asset
  class; nullable (meaningful only when enabled).
- ``paper_trading_sessions.min_positions`` — frozen minimum position count (surfaced,
  not fabricated); nullable (meaningful only when enabled).
- ``paper_trading_sessions.max_invested_pct`` — frozen maximum invested fraction (cash
  buffer); nullable (meaningful only when enabled).

The per-asset cap reuses the existing ``max_allocation_pct`` column (left at its 1.0 =
no-cap value for existing rows), so no new column is added for it.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: str | Sequence[str] | None = 'b3c4d5e6f7a8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "paper_trading_sessions",
        sa.Column(
            "risk_guardrails_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.execute(
        "UPDATE paper_trading_sessions SET risk_guardrails_enabled = false "
        "WHERE risk_guardrails_enabled IS NULL"
    )
    op.add_column(
        "paper_trading_sessions",
        sa.Column("max_asset_class_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "paper_trading_sessions",
        sa.Column("min_positions", sa.Integer(), nullable=True),
    )
    op.add_column(
        "paper_trading_sessions",
        sa.Column("max_invested_pct", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("paper_trading_sessions", "max_invested_pct")
    op.drop_column("paper_trading_sessions", "min_positions")
    op.drop_column("paper_trading_sessions", "max_asset_class_pct")
    op.drop_column("paper_trading_sessions", "risk_guardrails_enabled")
