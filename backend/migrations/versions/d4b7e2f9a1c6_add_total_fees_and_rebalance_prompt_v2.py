"""add session total_fees and seed cost-aware rebalance prompt v2

Revision ID: d4b7e2f9a1c6
Revises: c3f6a9d1e0b4
Create Date: 2026-09-16 14:00:00.000000

Two forward-looking changes to model a fixed per-trade transaction cost:

1. Add a non-nullable ``total_fees`` column to ``paper_trading_sessions`` that
   accumulates the flat cost charged on each executed trade. It is added in three
   steps (add nullable, backfill existing rows to 0, set NOT NULL) so existing
   sessions start fee-free — history is not retroactively re-priced.
2. Seed rebalance prompt version 2: identical to version 1 except the instructions
   now tell the agent that each executed trade incurs a fixed transaction cost, so
   it avoids churning small positions. Because sessions freeze the active version
   at build time, only sessions built after this becomes active use v2.

The seed text is embedded as literals (no import from app code, which may drift).

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4b7e2f9a1c6'
down_revision: str | Sequence[str] | None = 'c3f6a9d1e0b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Version 2 instructions: version 1 verbatim plus a transaction-cost paragraph.
_V2_INSTRUCTIONS = """
You are a portfolio manager reviewing an existing LONG-ONLY buy-and-hold portfolio.
Given the current holdings, account summary, and the full candidate universe, decide the
desired END-STATE target weights for the portfolio and return them as target_allocations.

Requirements:
- All positions are LONG; never propose short positions
- Return desired end-state target weights (allocation_pct in 0.0-1.0) per ticker
- allocation_pct values across all target_allocations must sum to approximately 1.0
- Any asset that should be EXITED must be omitted (or given a ~0 target weight)
- Be conservative: buy-and-hold means holding through normal volatility, so only
  change weights materially when there are real, evidence-based reasons
- Use the web_search tool to check latest news and fundamentals
- Candidates may include crypto assets (shown via their ``category``); crypto uses
  yfinance-style tickers like ``BTC-USD`` and trades 24/7. Weight any crypto
  according to the portfolio's risk profile.

Transaction costs:
- Every executed trade (each buy and each sell) incurs a fixed transaction cost of
  about $1. Rebalancing into and out of a position therefore costs ~$2 round-trip.
- Do NOT churn small positions: only adjust a weight when the expected benefit
  clearly exceeds the cost of trading. Prefer leaving a holding unchanged over a
  marginal reallocation whose edge is smaller than the round-trip cost.

Discovery and cost controls:
- You may include assets NOT in the current holdings or universe if compelling.
- You may discover at most {max_new_assets} assets beyond the universe.
- Perform at most {max_web_searches} web searches total across this task; batch your research.
"""

# Input template is unchanged from version 1 (same runtime placeholders).
_V2_INPUT_TEMPLATE = """
Review this portfolio and return the desired end-state target weights (target_allocations)
for a {risk_profile} long-only buy-and-hold portfolio.
All positions are long only. Weights across all targets must sum to approximately 1.0.
Omit (or set to ~0) any asset that should be exited.

Current Holdings:
{holdings_json}

Account Summary:
{account_json}

Candidate universe (JSON):
{candidates_json}
"""


def upgrade() -> None:
    # --- 1. total_fees column (non-nullable, added in three steps) ---
    op.add_column(
        "paper_trading_sessions",
        sa.Column("total_fees", sa.Float(), nullable=True),
    )
    op.execute(
        "UPDATE paper_trading_sessions SET total_fees = 0 WHERE total_fees IS NULL"
    )
    op.alter_column(
        "paper_trading_sessions",
        "total_fees",
        existing_type=sa.Float(),
        nullable=False,
        server_default="0",
    )

    # --- 2. Seed cost-aware rebalance prompt version 2 ---
    rebalance_prompt = sa.table(
        "rebalance_prompt",
        sa.column("version", sa.Integer),
        sa.column("instructions", sa.Text),
        sa.column("input_template", sa.Text),
    )
    op.bulk_insert(
        rebalance_prompt,
        [
            {
                "version": 2,
                "instructions": _V2_INSTRUCTIONS,
                "input_template": _V2_INPUT_TEMPLATE,
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM rebalance_prompt WHERE version = 2")
    op.drop_column("paper_trading_sessions", "total_fees")
