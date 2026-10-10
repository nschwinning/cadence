"""AI-portfolio service: orchestration for build and rebalance jobs.

Routers/background jobs stay thin and delegate here. A job's whole lifecycle is
recorded on an ``ai_portfolio_events`` row while persistence of the portfolio,
the paper-trading session, its trades, runs, and closed positions is reused from
the portfolios and paper-trading domains (never re-implemented here).

- **Build**: run the agent → create an AI-managed :class:`Portfolio` and a
  :class:`PaperTradingSession` → size and place opening orders via the
  :class:`AIPortfolioExecutor` against the :class:`Broker` → record trades + a
  session run → mark the event ``succeeded``/``partial``/``failed``.
- **Rebalance**: guard on ``broker.is_market_open()`` (record a ``skipped`` run
  and event when closed) → read positions/account → run the agent → close then
  open via the executor → record trades + closed positions + a session run →
  mark the event terminal.

This module is a thin facade: the implementation lives in cohesive submodules
(``params``, ``_helpers``, ``notifications``, ``prompts``, ``events``,
``snapshots``, ``stop_loss`` and ``flows.*``) and is re-exported here so the whole
public API stays importable as ``cadence.ai_portfolio.service.<name>``.
"""

from __future__ import annotations

from cadence.ai_portfolio._helpers import _exclude_unexecutable_candidates
from cadence.ai_portfolio.events import (
    build_orders_settled,
    count_ai_runs,
    count_session_events,
    create_build_event,
    create_close_event,
    create_rebalance_event,
    get_event,
    get_inflight_rebalance_event,
    list_ai_runs,
    list_session_events,
    session_allows_crypto,
    session_involves_crypto,
)
from cadence.ai_portfolio.flows.build import run_build_event
from cadence.ai_portfolio.flows.close import close_session
from cadence.ai_portfolio.flows.rebalance import run_rebalance_event
from cadence.ai_portfolio.params import AIBuildParams
from cadence.ai_portfolio.prompts import (
    get_active_rebalance_prompt,
    get_rebalance_prompt_by_version,
)
from cadence.ai_portfolio.snapshots import (
    assemble_daily_run_snapshots,
    snapshot_all_sessions,
)
from cadence.ai_portfolio.stop_loss import (
    StopLossOutcome,
    _trading_days_ahead,
    scan_stop_losses,
)

__all__ = [
    "AIBuildParams",
    "StopLossOutcome",
    "_exclude_unexecutable_candidates",
    "_trading_days_ahead",
    "assemble_daily_run_snapshots",
    "build_orders_settled",
    "close_session",
    "count_ai_runs",
    "count_session_events",
    "create_build_event",
    "create_close_event",
    "create_rebalance_event",
    "get_active_rebalance_prompt",
    "get_event",
    "get_inflight_rebalance_event",
    "get_rebalance_prompt_by_version",
    "list_ai_runs",
    "list_session_events",
    "run_build_event",
    "run_rebalance_event",
    "scan_stop_losses",
    "session_allows_crypto",
    "session_involves_crypto",
    "snapshot_all_sessions",
]
