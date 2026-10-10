"""Push-notification formatters and best-effort delivery for the AI service.

Builds the message bodies for daily P&L snapshots, executed/skipped rebalances and
stop-outs, and wraps :class:`Notifier` sends so a misbehaving notifier can never
turn a successful run into a failure. Imports only the shared helpers (for
:func:`_order_action`) so snapshots/stop-loss/flows can depend on it freely.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from cadence.ai_portfolio._helpers import _order_action
from cadence.ai_portfolio.executor import TradeResult
from cadence.notify.base import Notifier
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.benchmark import (
    benchmark_return_fraction,
    load_benchmark_series,
)
from cadence.paper_trading.constants import Benchmark, benchmark_display_name

logger = logging.getLogger(__name__)


def _signed_money(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}${abs(value):,.2f}"


def _signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}{abs(value) * 100:.2f}%"


def _sharpe_text(sharpe: float | None) -> str:
    """Signed Sharpe to 2dp, or an em dash until enough history exists."""
    return f"{sharpe:+.2f}" if sharpe is not None else "—"


def _best_worst_line(holdings: list[tuple[str, float]]) -> str | None:
    """The best/worst individual holding by return, or ``None`` when none held."""
    if not holdings:
        return None
    best = max(holdings, key=lambda h: h[1])
    worst = min(holdings, key=lambda h: h[1])
    return (
        f"Best: {best[0]} {_signed_pct(best[1])}   "
        f"Worst: {worst[0]} {_signed_pct(worst[1])}"
    )


def _session_snapshot_message(
    snapshot: Any,
    kpis: Any,
    benchmark_suffix: str | None,
    holdings: list[tuple[str, float]],
) -> str:
    """Build one session's daily push body.

    The portfolio name lives in the push title, so the body leads with the day's
    value + P&L, then headline KPIs (total return, realized/unrealized P&L,
    unallocated cash, fees, Sharpe), the benchmark comparison (when available), and
    the session's own best/worst holding (when it holds anything).
    """
    lines = [
        (
            f"${snapshot.total_value:,.2f} today "
            f"({_signed_money(snapshot.daily_pnl)}, "
            f"{_signed_pct(snapshot.daily_pnl_pct)})"
        ),
        (
            f"Total return: {_signed_money(kpis.total_return)} "
            f"({_signed_pct(kpis.total_return_pct)})"
        ),
        (
            f"Realized {_signed_money(kpis.realised_pnl)} · "
            f"Unrealized {_signed_money(kpis.unrealised_pnl)} · "
            f"Cash ${kpis.unallocated_cash:,.2f} · "
            f"Fees ${kpis.total_fees:,.2f}"
        ),
        f"Sharpe: {_sharpe_text(kpis.sharpe_ratio)}",
    ]
    if benchmark_suffix is not None:
        lines.append(benchmark_suffix)
    best_worst = _best_worst_line(holdings)
    if best_worst is not None:
        lines.append(best_worst)
    return "\n".join(lines)


def _benchmark_suffix(
    session: Session,
    session_row: Any,
    snapshot: Any,
    *,
    as_of: date,
) -> str | None:
    """Benchmark comparison suffix for a session's report line, or ``None``.

    Computes the session's benchmark buy-and-hold return over the period (from its
    first snapshot date to ``as_of``, using stored prices) and the excess return
    (session time-weighted total return − benchmark return). The session leg is
    time-weighted and contribution-aware so a mid-session capital increase is not
    counted as a gain. Returns ``None`` when the session has no snapshots or the
    benchmark lacks usable stored prices, so the caller omits the suffix.
    """
    snapshots = paper_service.list_value_snapshots(
        session, session_id=session_row.id
    )
    if not snapshots:
        return None
    series = load_benchmark_series(session, session_row.benchmark)
    benchmark_return = benchmark_return_fraction(
        series, start_date=snapshots[0].snapshot_date, as_of=as_of
    )
    if benchmark_return is None:
        return None
    events = paper_service.list_capital_events(session, session_id=session_row.id)
    contributions = paper_service.session_contributions(
        session_row, events, start_date=snapshots[0].snapshot_date
    )
    total_return_pct = paper_service.time_weighted_return(
        snapshots, contributions, live_value=snapshot.total_value, as_of=as_of
    )
    excess = total_return_pct - benchmark_return
    name = benchmark_display_name(Benchmark(session_row.benchmark))
    return (
        f"vs {name}: {_signed_pct(benchmark_return)} "
        f"(excess {_signed_pct(excess)})"
    )


def _notify_safely(notifier: Notifier, *, title: str, message: str) -> None:
    """Send a notification, swallowing any failure.

    The :class:`Notifier` contract already forbids raising, but this guards the
    call site defensively so a misbehaving implementation can never turn a
    successful rebalance into a failure.
    """
    try:
        notifier.send(message, title=title)
    except Exception:
        # Notifications are strictly best-effort: a broken notifier must never
        # turn a successful (or already-failed) rebalance into something worse.
        logger.warning("rebalance notification failed", exc_info=True)


def _notify_rebalance_skipped(
    notifier: Notifier | None,
    portfolio_name: str,
    reason: str,
    *,
    crypto_only: bool,
) -> None:
    """Inform the user that a session's engaged rebalance was skipped as a no-op.

    Sent only for a session the run actually engaged (selected, planned, evaluated)
    that then skipped — the pre-agent crypto-only skip and the post-plan buy-only
    skip — so the user knows the scheduled rebalance did nothing and why. A no-op
    when ``notifier`` is ``None`` (manual rebalances stay silent). Sessions filtered
    out before processing (scope-excluded weekend sessions, weekend stocks-only
    snapshot skips) never reach here and stay silent. Distinct from the
    trade-success push, which fires only when orders execute.
    """
    if notifier is None:
        return
    label = "crypto rebalance skipped" if crypto_only else "rebalance skipped"
    _notify_safely(
        notifier,
        title=f"Cadence: {portfolio_name} {label}",
        message=f"{portfolio_name}: {label} — {reason}.",
    )


def _rebalance_success_message(
    portfolio_name: str,
    trade_results: list[TradeResult],
    realized_pnl: float,
) -> str:
    """Build the push body for an executed rebalance: per-order lines + P&L."""
    lines = [f"{portfolio_name}: rebalanced"]
    for tr in trade_results:
        if not tr.executed:
            continue
        action = _order_action(tr.side).value.upper()
        price = tr.filled_price if tr.filled_price is not None else tr.price
        at = f" @ ${price:,.2f}" if price is not None else ""
        lines.append(f"{action} {tr.shares:g} {tr.ticker}{at}")
    lines.append(f"Realized P&L: ${realized_pnl:,.2f}")
    return "\n".join(lines)


def _stop_loss_message(
    label: str,
    ticker: str,
    shares: float,
    exit_price: float,
    realized_pnl: float,
) -> str:
    """Build the push body for a single stop-out."""
    return (
        f"{label}: stop-loss triggered\n"
        f"SELL {shares:g} {ticker} @ ${exit_price:,.2f}\n"
        f"Realized P&L: ${realized_pnl:,.2f}"
    )
