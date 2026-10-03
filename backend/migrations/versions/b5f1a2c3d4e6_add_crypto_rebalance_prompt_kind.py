"""add crypto rebalance prompt kind and freeze crypto prompt version on session

Revision ID: b5f1a2c3d4e6
Revises: a9e4c7b2d8f1
Create Date: 2026-10-03 09:30:00.000000

Introduce the weekend crypto-only rebalance prompt family. The rebalance_prompt
table gains a ``kind`` discriminator (``rebalance`` | ``crypto_rebalance``) so the
two prompt families version independently; the old global-unique index on
``version`` is replaced by a unique constraint on ``(kind, version)``. Existing
rows default to ``rebalance``. A ``crypto_rebalance`` v1 prompt is seeded with
crypto-scoped instructions: only the crypto sleeve is rebalanced within the
provided crypto budget, and equities are never traded.

Paper-trading sessions gain a non-nullable ``crypto_rebalance_prompt_version``,
mirroring ``rebalance_prompt_version``: the weekend crypto-only run uses this
pinned version. Pre-existing sessions are backfilled to the seeded active crypto
version. The seed text is embedded as literals (no import from app code).

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b5f1a2c3d4e6'
down_revision: str | Sequence[str] | None = 'a9e4c7b2d8f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CRYPTO_V1_INSTRUCTIONS = """
You are a portfolio manager running a LONG-ONLY buy-and-hold strategy, rebalancing
ONLY the CRYPTO sleeve of the portfolio. The equities market is closed (this is a
weekend crypto-only run): you must NOT propose any equity positions, and any
equities currently held will be left completely untouched — do not try to sell,
trim, or fund trades from them.

You are given the current CRYPTO holdings, an account summary that includes the
crypto budget available to you, and a candidate universe of crypto assets only.
Decide the desired END-STATE target weights across the crypto sleeve and return
them as target_allocations. Your weights are applied to the crypto budget
(current crypto positions' market value + the session's unallocated cash), not to
the whole portfolio.

Requirements:
- Only CRYPTO assets; never propose equities or short positions.
- Return desired end-state target weights (allocation_pct in 0.0-1.0) per ticker.
- allocation_pct values across all target_allocations must sum to approximately 1.0;
  they distribute the crypto budget, not the entire portfolio.
- Any crypto asset that should be EXITED must be omitted (or given a ~0 target weight).
- Crypto uses yfinance-style tickers like ``BTC-USD`` and trades 24/7. Weight the
  sleeve according to the portfolio's risk profile.
- Use the web_search tool to check latest crypto news and fundamentals; batch your
  research.

Transaction costs:
- Every executed trade (each buy and each sell) incurs a fixed transaction cost of
  about $1. Rebalancing into and out of a position therefore costs ~$2 round-trip.
- Do NOT churn small positions: only adjust a weight when the expected benefit
  clearly exceeds the cost of trading. Prefer leaving a holding unchanged over a
  marginal reallocation whose edge is smaller than the round-trip cost.

Discovery and cost controls:
- You may include crypto assets NOT in the current holdings or universe if compelling.
- You may discover at most {max_new_assets} assets beyond the universe.
- Perform at most {max_web_searches} web searches total across this task; batch your research.
"""

# Input template: same runtime placeholders as the weekday prompt. The account
# summary carries the crypto budget; holdings/candidates are crypto-only.
_CRYPTO_V1_INPUT_TEMPLATE = """
Review this CRYPTO sleeve and return the desired end-state target weights (target_allocations)
for the {risk_profile} long-only crypto sleeve of a buy-and-hold portfolio.
All positions are long only and CRYPTO only. Weights across all targets must sum to
approximately 1.0 and distribute the crypto budget shown in the account summary.
Omit (or set to ~0) any crypto asset that should be exited. Do NOT propose equities;
equity holdings are not part of this run and will not be traded.

Current Crypto Holdings:
{holdings_json}

Account Summary (includes crypto_budget):
{account_json}

Candidate universe (crypto only, JSON):
{candidates_json}
"""


def upgrade() -> None:
    # 1. rebalance_prompt.kind discriminator; existing rows default to 'rebalance'.
    op.add_column(
        "rebalance_prompt",
        sa.Column(
            "kind",
            sa.Enum(
                "rebalance",
                "crypto_rebalance",
                name="promptkind",
                native_enum=False,
            ),
            nullable=False,
            server_default="rebalance",
        ),
    )
    # Replace the global-unique index on version with a per-(kind, version) scheme.
    op.drop_index("ix_rebalance_prompt_version", table_name="rebalance_prompt")
    op.create_index(
        "idx_rebalance_prompt_kind_version",
        "rebalance_prompt",
        ["kind", "version"],
    )
    op.create_unique_constraint(
        "uq_rebalance_prompt_kind_version",
        "rebalance_prompt",
        ["kind", "version"],
    )

    # 2. Seed the crypto_rebalance v1 prompt.
    rebalance_prompt = sa.table(
        "rebalance_prompt",
        sa.column("kind", sa.Text),
        sa.column("version", sa.Integer),
        sa.column("instructions", sa.Text),
        sa.column("input_template", sa.Text),
    )
    op.bulk_insert(
        rebalance_prompt,
        [
            {
                "kind": "crypto_rebalance",
                "version": 1,
                "instructions": _CRYPTO_V1_INSTRUCTIONS,
                "input_template": _CRYPTO_V1_INPUT_TEMPLATE,
            }
        ],
    )

    # 3. Freeze the crypto prompt version on each session (nullable → backfill → NOT NULL).
    op.add_column(
        "paper_trading_sessions",
        sa.Column("crypto_rebalance_prompt_version", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE paper_trading_sessions "
        "SET crypto_rebalance_prompt_version = "
        "(SELECT MAX(version) FROM rebalance_prompt WHERE kind = 'crypto_rebalance') "
        "WHERE crypto_rebalance_prompt_version IS NULL"
    )
    op.alter_column(
        "paper_trading_sessions",
        "crypto_rebalance_prompt_version",
        existing_type=sa.Integer(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("paper_trading_sessions", "crypto_rebalance_prompt_version")
    op.execute("DELETE FROM rebalance_prompt WHERE kind = 'crypto_rebalance'")
    op.drop_constraint(
        "uq_rebalance_prompt_kind_version",
        "rebalance_prompt",
        type_="unique",
    )
    op.drop_index(
        "idx_rebalance_prompt_kind_version", table_name="rebalance_prompt"
    )
    op.create_index(
        "ix_rebalance_prompt_version",
        "rebalance_prompt",
        ["version"],
        unique=True,
    )
    op.drop_column("rebalance_prompt", "kind")
