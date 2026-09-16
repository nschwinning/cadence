"""add versioned rebalance_prompt table and seed version 1

Revision ID: a1d4e7c2b9f8
Revises: b8c1e2f3a4d5
Create Date: 2026-09-16 12:00:00.000000

The AI rebalance prompt is moved out of application code into a versioned table.
Each row is one immutable prompt version; the active prompt is the highest
``version``. Version 1 is seeded here with the exact text that was hardcoded at
the time of this change, so behavior is unchanged on first deploy. The seed text
is embedded as literals (no import from app code, which may drift). The ``{name}``
tokens are placeholders the agent fills at run time.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1d4e7c2b9f8'
down_revision: str | Sequence[str] | None = 'b8c1e2f3a4d5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SEED_INSTRUCTIONS = """
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

Discovery and cost controls:
- You may include assets NOT in the current holdings or universe if compelling.
- You may discover at most {max_new_assets} assets beyond the universe.
- Perform at most {max_web_searches} web searches total across this task; batch your research.
"""

_SEED_INPUT_TEMPLATE = """
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
    """Upgrade schema."""
    rebalance_prompt = op.create_table(
        'rebalance_prompt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=False),
        sa.Column('input_template', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_rebalance_prompt_version'),
        'rebalance_prompt',
        ['version'],
        unique=True,
    )
    op.bulk_insert(
        rebalance_prompt,
        [
            {
                'version': 1,
                'instructions': _SEED_INSTRUCTIONS,
                'input_template': _SEED_INPUT_TEMPLATE,
            }
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_rebalance_prompt_version'), table_name='rebalance_prompt')
    op.drop_table('rebalance_prompt')
