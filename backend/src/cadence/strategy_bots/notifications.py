"""Push-notification formatters and best-effort delivery for the strategy bots.

Parallels :mod:`cadence.ai_portfolio.notifications`: builds the message bodies for
the drawdown kill-switch event and the evening per-bot daily summary, and wraps
:class:`Notifier` sends so a misbehaving (or absent) notifier can never turn a
successful tick or snapshot job into a failure. Message construction is kept pure
and free of DB access so it stays unit-testable; the service supplies the computed
figures (daily P&L, Sharpe, benchmark suffix, trade count).
"""

from __future__ import annotations

import logging
from typing import Any

from cadence.notify.base import Notifier

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
    """The best/worst individual position by return, or ``None`` when none held."""
    if not holdings:
        return None
    best = max(holdings, key=lambda h: h[1])
    worst = min(holdings, key=lambda h: h[1])
    return (
        f"Best: {best[0]} {_signed_pct(best[1])}   "
        f"Worst: {worst[0]} {_signed_pct(worst[1])}"
    )


def _kill_switch_message(
    liquidated_tickers: list[str], realised_pnl: float
) -> str:
    """Build the push body for a drawdown kill-switch trip.

    Names the positions liquidated (count + tickers), the realised P&L booked on the
    liquidation, and that the bot is now stopped. The bot's label lives in the push
    title, so the body leads with the event.
    """
    if liquidated_tickers:
        liquidation = (
            f"Liquidated {len(liquidated_tickers)} position(s): "
            f"{', '.join(liquidated_tickers)}"
        )
    else:
        liquidation = "No open positions to liquidate"
    return "\n".join(
        [
            "Drawdown kill-switch tripped.",
            liquidation,
            f"Realized P&L: {_signed_money(realised_pnl)}",
            "Bot is now stopped.",
        ]
    )


def _bot_summary_message(
    kpis: Any,
    *,
    daily_pnl: float,
    daily_pnl_pct: float | None,
    cash: float,
    trades_today: int,
    benchmark_suffix: str | None,
    holdings: list[tuple[str, float]],
) -> str:
    """Build one bot's evening daily-summary push body.

    Mirrors the AI daily report (:func:`ai_portfolio.notifications._session_snapshot_message`):
    the bot's label lives in the push title, so the body leads with the day's value +
    P&L, then headline KPIs (total return, realized/unrealized P&L, cash, fees, Sharpe),
    the benchmark comparison (when available), the best/worst open position (when any),
    and finally the number of trades executed that day. The day-over-day percent is
    omitted when the baseline is non-positive (e.g. an empty day-one baseline).
    """
    if daily_pnl_pct is not None:
        value_line = (
            f"${kpis.current_value:,.2f} today "
            f"({_signed_money(daily_pnl)}, {_signed_pct(daily_pnl_pct)})"
        )
    else:
        value_line = (
            f"${kpis.current_value:,.2f} today ({_signed_money(daily_pnl)})"
        )
    lines = [
        value_line,
        (
            f"Total return: {_signed_money(kpis.total_return)} "
            f"({_signed_pct(kpis.total_return_pct)})"
        ),
        (
            f"Realized {_signed_money(kpis.realised_pnl)} · "
            f"Unrealized {_signed_money(kpis.unrealised_pnl)} · "
            f"Cash ${cash:,.2f} · "
            f"Fees ${kpis.total_fees:,.2f}"
        ),
        f"Sharpe: {_sharpe_text(kpis.sharpe_ratio)}",
    ]
    if benchmark_suffix is not None:
        lines.append(benchmark_suffix)
    best_worst = _best_worst_line(holdings)
    if best_worst is not None:
        lines.append(best_worst)
    lines.append(f"Trades today: {trades_today}")
    return "\n".join(lines)


def _notify_safely(
    notifier: Notifier | None, *, title: str, message: str
) -> None:
    """Send a notification, no-op on a null notifier, swallowing any failure.

    Notifications are strictly best-effort: an absent notifier sends nothing and a
    misbehaving one must never turn a successful (or already-failed) tick or snapshot
    job into something worse.
    """
    if notifier is None:
        return
    try:
        notifier.send(message, title=title)
    except Exception:
        logger.warning("bot notification failed", exc_info=True)
