"""Unit tests for the stopped-bot summary agent's prompt and output wiring.

No network calls: these exercise the deterministic prompt builder, confirm the
agent is constructed with the Pydantic ``output_type``, surface timeouts as the
domain error, and check the in-memory fake returns a canned recap.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from tests.fakes import FakeBotSummaryAgent

from cadence.agents import build_agent
from cadence.strategy_bots import summary_agent as agent_module
from cadence.strategy_bots.errors import BotSummaryUnavailableError
from cadence.strategy_bots.service import SessionSummaryStats, TradeExtreme
from cadence.strategy_bots.summary_agent import (
    BotSummaryOutput,
    OpenAIBotSessionSummaryAgent,
    build_bot_summary_prompt,
)


def _trade(ticker: str, pnl: float) -> TradeExtreme:
    return TradeExtreme(
        ticker=ticker,
        realised_pnl=pnl,
        quantity=10.0,
        entry_price=50.0,
        entry_at=datetime(2026, 1, 6, 9, 0, tzinfo=UTC),
        exit_price=55.0,
        exit_at=datetime(2026, 1, 7, 9, 0, tzinfo=UTC),
    )


def _stats(**overrides: object) -> SessionSummaryStats:
    base: dict[str, object] = {
        "stop_reason": "drawdown_kill_switch",
        "stopped_at": datetime(2026, 1, 8, 16, 0, tzinfo=UTC),
        "started_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        "lifespan_days": 7,
        "final_value": 98_500.0,
        "allocated_capital": 100_000.0,
        "total_return": -1_500.0,
        "total_return_pct": -0.015,
        "realised_pnl": -1_500.0,
        "peak_value": 105_000.0,
        "max_drawdown": 0.0619,
        "trade_count": 2,
        "win_rate": 0.5,
        "best_trade": _trade("AAPL", 50.0),
        "worst_trade": _trade("MSFT", -200.0),
        "benchmark": "SP500",
        "benchmark_return_pct": 0.02,
        "excess_return_pct": -0.035,
    }
    base.update(overrides)
    return SessionSummaryStats(**base)  # type: ignore[arg-type]


def test_prompt_includes_key_stats_and_stop_reason() -> None:
    prompt = build_bot_summary_prompt(_stats())

    assert "the drawdown kill-switch fired" in prompt
    assert "7 day(s) active" in prompt
    assert "$98,500.00" in prompt
    assert "-$1,500.00" in prompt
    assert "$105,000.00" in prompt  # peak
    assert "Closed trades: 2" in prompt
    assert "50%" in prompt  # win rate
    # Best/worst carry the exact entry/exit fills.
    assert "Best trade: AAPL +$50.00" in prompt
    assert "bought 10 @ $50.00 on 2026-01-06" in prompt
    assert "sold @ $55.00 on 2026-01-07" in prompt
    assert "Worst trade: MSFT -$200.00" in prompt
    # Benchmark comparison rendered.
    assert "SP500 returned +2.00%" in prompt
    # No forward-looking scoring requested.
    assert "numeric scores" in prompt


def test_prompt_handles_absent_trades_and_benchmark() -> None:
    prompt = build_bot_summary_prompt(
        _stats(
            stop_reason="manual",
            trade_count=0,
            win_rate=None,
            best_trade=None,
            worst_trade=None,
            benchmark_return_pct=None,
            excess_return_pct=None,
        )
    )

    assert "it was stopped manually" in prompt
    assert "n/a (no closed trades)" in prompt
    assert "Best trade: none (no closed trades)" in prompt
    assert "SP500 (no comparable return yet)" in prompt


def test_prompt_is_deterministic_for_fixed_stats() -> None:
    stats = _stats()

    assert build_bot_summary_prompt(stats) == build_bot_summary_prompt(stats)


def test_fake_agent_returns_canned_output() -> None:
    agent = FakeBotSummaryAgent()

    output = agent.summarize(_stats())

    assert isinstance(output, BotSummaryOutput)
    assert output.headline
    assert output.narrative
    assert agent.calls == 1


def test_summarize_raises_domain_error_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NeverFinishes:
        @staticmethod
        async def run(*args: object, **kwargs: object) -> object:
            await asyncio.sleep(1)
            raise AssertionError("should have timed out")  # pragma: no cover

    monkeypatch.setattr(agent_module, "Runner", _NeverFinishes)
    monkeypatch.setattr(
        agent_module.settings, "RECOMMENDER_AGENT_TIMEOUT_SECONDS", 0
    )

    with pytest.raises(BotSummaryUnavailableError) as excinfo:
        OpenAIBotSessionSummaryAgent().summarize(_stats())

    assert "timed out" in str(excinfo.value)


def test_summary_agent_uses_pydantic_output_type() -> None:
    agent = build_agent(
        name="BotSessionSummaryAgent",
        instructions="x",
        output_type=BotSummaryOutput,
    )
    assert agent.output_type is BotSummaryOutput
