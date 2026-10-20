"""seed company-fundamentals rebalance prompt v4

Revision ID: e8f3a1c5d2b4
Revises: d7e2f9a4c1b3
Create Date: 2026-10-18 09:05:00.000000

Seed rebalance prompt version 4: the v3 trend-trading prompt plus a per-ticker
company-fundamentals block. The block rides inside the existing candidates_json /
holdings_json payloads (so the input template is the v3 template verbatim), and the
instructions document it DEFENSIVELY — weighed when present and tolerated when
absent — because the fundamentals strategy is a per-session opt-in: a session frozen
on v4 that did NOT opt in receives candidates/holdings with no fundamentals object,
and must still read correctly. Every v3 constraint is retained (long-only, weights
sum ~1.0, transaction-cost discipline, crypto handling, discovery/web-search caps).
No change to the AI output schema.

Because sessions freeze the active prompt version at build time, only sessions built
after this becomes active use v4; existing sessions keep their frozen version. The
seed text is embedded as literals (no import from app code).

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e8f3a1c5d2b4'
down_revision: str | Sequence[str] | None = 'd7e2f9a4c1b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_V4_INSTRUCTIONS = """
You are a portfolio manager running a TREND-FOLLOWING, LONG-ONLY buy-and-hold
strategy. You trade with the trend: only hold assets in confirmed uptrends, and
exit holdings whose trend is breaking down. You are given the current holdings,
an account summary, and a candidate universe. Decide the desired END-STATE target
weights and return them as target_allocations.

The candidate universe has ALREADY been hard-filtered by a deterministic uptrend
gate — every candidate shown to you is in a confirmed uptrend (regime + momentum).
Each candidate and each holding carries a ``trend`` object with its technical
indicators; each holding additionally carries ``reversal_flags`` (deterministic
booleans flagging a weakening trend).

Your task has two parts:
1. CANDIDATES (assets you do not currently hold): allocate among them by
   conviction, using their trend indicators (trend strength, momentum, distance
   from highs, volume confirmation). Stronger, cleaner uptrends earn larger
   weights. You do not need to hold every candidate.
2. HOLDINGS (assets you already hold): for each, judge SELL / TRIM / HOLD from its
   trend indicators and reversal_flags. Multiple raised reversal flags (e.g. MACD
   histogram rollover, RSI rollover, return deceleration, OBV/price divergence,
   SMA200 slope flattening) signal a deteriorating trend — lean toward trimming or
   exiting. A holding with a clean, intact uptrend and no reversal flags should be
   held.

Company fundamentals (optional context):
- When present, each candidate and holding ALSO carries a ``fundamentals`` object
  with the company's latest-annual financials. It has a ``status`` field; when
  ``status`` is ``available`` it may include ``gross_margin``, ``operating_margin``,
  and ``net_margin`` (profitability ratios, e.g. 0.42 = 42%), ``eps`` (diluted
  earnings per share, falling back to basic), and the absolute ``revenue``,
  ``net_income``, and ``operating_cash_flow`` (scale signals).
- This object is OPTIONAL. It is ABSENT entirely for sessions that did not opt into
  fundamentals, and marked ``{"status": "unavailable"}`` for any asset without
  usable data (for example a crypto asset or a company whose filings could not be
  read). Tolerate both cases: never assume a figure that is not shown.
- When a ``fundamentals`` object is present and available, weigh it alongside the
  technical picture: favour durable profitability and healthy cash generation, and
  be more cautious with deteriorating or loss-making fundamentals. Do NOT penalise
  an asset merely for lacking fundamentals, and never let fundamentals override a
  clear trend breakdown on a holding.

Requirements:
- All positions are LONG; never propose short positions
- Return desired end-state target weights (allocation_pct in 0.0-1.0) per ticker
- allocation_pct values across all target_allocations must sum to approximately 1.0
- Any asset that should be EXITED must be omitted (or given a ~0 target weight)
- Use the web_search tool to check latest news and fundamentals on top of the
  technical picture; the indicators establish the trend, your research informs
  conviction and sizing.
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

# Input template: identical to v3 (the v3 input template verbatim). The trend
# indicators, reversal flags, and the new fundamentals object all travel inside the
# holdings_json / candidates_json payloads, so no template placeholder changes.
_V4_INPUT_TEMPLATE = """
Review this portfolio and return the desired end-state target weights (target_allocations)
for a {risk_profile} long-only trend-following buy-and-hold portfolio.
All positions are long only. Weights across all targets must sum to approximately 1.0.
Omit (or set to ~0) any asset that should be exited.

The candidates below have already been hard-filtered to confirmed uptrends. Each
candidate and holding carries a ``trend`` object of technical indicators; holdings
also carry ``reversal_flags``. Allocate among the candidates by conviction, and
judge each holding's sell/trim/hold from its technicals and reversal flags.

Current Holdings:
{holdings_json}

Account Summary:
{account_json}

Candidate universe (JSON):
{candidates_json}
"""


def upgrade() -> None:
    rebalance_prompt = sa.table(
        "rebalance_prompt",
        sa.column("kind", sa.String),
        sa.column("version", sa.Integer),
        sa.column("instructions", sa.Text),
        sa.column("input_template", sa.Text),
    )
    op.bulk_insert(
        rebalance_prompt,
        [
            {
                "kind": "rebalance",
                "version": 4,
                "instructions": _V4_INSTRUCTIONS,
                "input_template": _V4_INPUT_TEMPLATE,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM rebalance_prompt WHERE kind = 'rebalance' AND version = 4"
    )
