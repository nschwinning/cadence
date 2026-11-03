"""Unit tests for the strategy-bot notification message builders + send guard."""

from __future__ import annotations

from types import SimpleNamespace

from tests.fakes import RecordingNotifier

from cadence.strategy_bots.notifications import (
    _bot_summary_message,
    _kill_switch_message,
    _notify_safely,
)


def _kpis(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "current_value": 101_000.0,
        "total_return": 1_000.0,
        "total_return_pct": 0.01,
        "realised_pnl": 400.0,
        "unrealised_pnl": 600.0,
        "total_fees": 12.0,
        "sharpe_ratio": 1.25,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# Best-effort send guard (Task 1.1) --------------------------------------
def test_notify_safely_none_notifier_sends_nothing() -> None:
    # No notifier at all: a no-op (nothing to assert beyond "does not raise").
    _notify_safely(None, title="t", message="m")


def test_notify_safely_swallows_a_raising_notifier() -> None:
    notifier = RecordingNotifier(raises=True)
    # Must not propagate even though the notifier raises.
    _notify_safely(notifier, title="t", message="m")
    assert notifier.sent == [("m", "t")]


def test_notify_safely_delivers_to_a_working_notifier() -> None:
    notifier = RecordingNotifier()
    _notify_safely(notifier, title="Title", message="Body")
    assert notifier.sent == [("Body", "Title")]


# Kill-switch message (Task 1.2) -----------------------------------------
def test_kill_switch_message_lists_positions_pnl_and_stopped() -> None:
    message = _kill_switch_message(["AAPL", "MSFT"], -1_234.5)
    assert "Drawdown kill-switch tripped." in message
    assert "Liquidated 2 position(s): AAPL, MSFT" in message
    assert "Realized P&L: −$1,234.50" in message
    assert "Bot is now stopped." in message


def test_kill_switch_message_handles_no_open_positions() -> None:
    message = _kill_switch_message([], 0.0)
    assert "No open positions to liquidate" in message
    assert "+$0.00" in message


# Daily summary message (Task 1.3) ---------------------------------------
def test_bot_summary_message_mirrors_ai_figures_plus_trade_count() -> None:
    message = _bot_summary_message(
        _kpis(),
        daily_pnl=250.0,
        daily_pnl_pct=0.0025,
        cash=50_000.0,
        trades_today=3,
        benchmark_suffix="vs S&P 500: +0.10% (excess −0.09%)",
        holdings=[("AAPL", 0.05), ("MSFT", -0.02)],
    )
    assert "$101,000.00 today (+$250.00, +0.25%)" in message
    assert "Total return: +$1,000.00 (+1.00%)" in message
    assert (
        "Realized +$400.00 · Unrealized +$600.00 · Cash $50,000.00 · Fees $12.00"
        in message
    )
    assert "Sharpe: +1.25" in message
    assert "vs S&P 500: +0.10% (excess −0.09%)" in message
    assert "Best: AAPL +5.00%   Worst: MSFT −2.00%" in message
    assert "Trades today: 3" in message


def test_bot_summary_message_omits_absent_sharpe_and_benchmark() -> None:
    message = _bot_summary_message(
        _kpis(sharpe_ratio=None),
        daily_pnl=-10.0,
        daily_pnl_pct=None,
        cash=1_000.0,
        trades_today=0,
        benchmark_suffix=None,
        holdings=[],
    )
    # No percent when the baseline is non-positive (day-one empty baseline).
    assert "$101,000.00 today (−$10.00)" in message
    # Missing Sharpe renders as an em dash, like the AI report.
    assert "Sharpe: —" in message
    # No benchmark line, no best/worst line, trade count still present.
    assert "vs " not in message
    assert "Best:" not in message
    assert "Trades today: 0" in message
