"""The stopped-bot session-summary agent and its structured contract.

When a strategy-bot session stops (manually or via the drawdown kill-switch) the
app offers a short narrative recap of how the session went. The agent is given a
compact, deterministic rendering of the session's curated stats
(:class:`~cadence.strategy_bots.service.SessionSummaryStats`) and returns a
Pydantic :class:`BotSummaryOutput`. :class:`BotSessionSummaryAgent` is the seam
service code depends on so tests can swap in a fake with no network. Like the
asset-universe evaluation it mirrors, this agent uses no tools: it judges only the
supplied stats.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from agents.run import Runner
from pydantic import BaseModel, Field

from cadence.agents import build_agent, run_config_for_trace
from cadence.config import settings
from cadence.strategy_bots.errors import BotSummaryUnavailableError

if TYPE_CHECKING:
    from cadence.strategy_bots.service import SessionSummaryStats, TradeExtreme

_AGENT_NAME = "BotSessionSummaryAgent"

_AGENT_INSTRUCTIONS = """
You are a trading analyst writing a short, plain-language recap of a paper-trading
strategy bot that has stopped. You are given the session's final statistics — how
it stopped, how long it ran, its final value and total return, its high-water mark
and worst drawdown, its closed-trade record and win rate, its best and worst
round-trip, and how it did versus its benchmark.

Write a concise, honest markdown narrative of how the session went: lead with the
outcome, explain what drove it (the trade record, the drawdown, the benchmark
comparison), and note anything the figures make clear. If the bot was stopped by
the drawdown kill-switch, say so and frame the result relative to its peak. Judge
only the figures you are given; do not invent trades, prices, or facts not present.
Do not give forward-looking advice or predictions, and do not assign numeric scores
or ratings. Keep it to a few short paragraphs.
""".strip()


class BotSummaryOutput(BaseModel):
    """The agent's structured recap of a stopped session."""

    headline: str = Field(
        description="A single short sentence summarising the outcome",
    )
    narrative: str = Field(
        description="Markdown prose recapping how the session went",
    )


@runtime_checkable
class BotSessionSummaryAgent(Protocol):
    """Seam for producing an AI recap of a stopped bot session.

    Implemented by :class:`OpenAIBotSessionSummaryAgent` in production and by a
    fake in tests. ``summarize`` is synchronous so the service stays fully sync;
    the real implementation drives the async SDK internally.
    """

    def summarize(self, stats: SessionSummaryStats) -> BotSummaryOutput:
        """Return a structured recap of the given session summary stats."""
        ...

    def build_prompt(self, stats: SessionSummaryStats) -> str:
        """Return the exact prompt text that would be sent for these stats."""
        ...


def _money(value: float) -> str:
    """Render a dollar amount as ``$1,234.56``."""
    return f"${value:,.2f}"


def _signed_money(value: float) -> str:
    """Render a signed dollar amount as ``+$12.34`` / ``-$12.34``."""
    sign = "+" if value >= 0 else "-"
    return f"{sign}{_money(abs(value))}"


def _pct(fraction: float) -> str:
    """Render a fraction as a signed percentage (``+1.23%``)."""
    return f"{fraction * 100:+.2f}%"


def _stop_reason_label(stop_reason: str | None) -> str:
    """Human label for a stop reason value (tolerant of nulls/unknowns)."""
    if stop_reason == "drawdown_kill_switch":
        return "the drawdown kill-switch fired"
    if stop_reason == "manual":
        return "it was stopped manually"
    return "it stopped (reason not recorded)"


def _render_trade(label: str, trade: TradeExtreme | None) -> str:
    """One ``label: ...`` line describing a round-trip, or a 'none' line."""
    if trade is None:
        return f"{label}: none (no closed trades)"
    return (
        f"{label}: {trade.ticker} {_signed_money(trade.realised_pnl)} "
        f"(bought {trade.quantity:g} @ {_money(trade.entry_price)} on "
        f"{trade.entry_at.date().isoformat()}, sold @ {_money(trade.exit_price)} on "
        f"{trade.exit_at.date().isoformat()})"
    )


def build_bot_summary_prompt(stats: SessionSummaryStats) -> str:
    """Compose the agent input from a session's summary stats.

    Pure and deterministic for a given stats block so it is unit-testable.
    """
    if stats.win_rate is None:
        win_rate_line = "n/a (no closed trades)"
    else:
        win_rate_line = f"{stats.win_rate * 100:.0f}%"
    if stats.benchmark_return_pct is None or stats.excess_return_pct is None:
        benchmark_line = f"{stats.benchmark} (no comparable return yet)"
    else:
        benchmark_line = (
            f"{stats.benchmark} returned {_pct(stats.benchmark_return_pct)}; "
            f"the bot's excess was {_pct(stats.excess_return_pct)}"
        )
    return f"""
Recap this stopped strategy-bot session.

How it stopped: {_stop_reason_label(stats.stop_reason)}.
Lifespan: {stats.lifespan_days} day(s) active.

Capital allocated: {_money(stats.allocated_capital)}
Final value: {_money(stats.final_value)}
Total return: {_signed_money(stats.total_return)} ({_pct(stats.total_return_pct)})
Realised P&L: {_signed_money(stats.realised_pnl)}
Peak value (high-water mark): {_money(stats.peak_value)}
Max drawdown (worst peak-to-trough): {stats.max_drawdown * 100:.2f}%

Closed trades: {stats.trade_count}
Win rate: {win_rate_line}
{_render_trade("Best trade", stats.best_trade)}
{_render_trade("Worst trade", stats.worst_trade)}

Benchmark: {benchmark_line}

Write a short markdown recap (a one-line headline plus a few short paragraphs) of
how this session went, grounded only in the figures above. No predictions, advice,
or numeric scores.
""".strip()


class OpenAIBotSessionSummaryAgent:
    """Production :class:`BotSessionSummaryAgent` backed by ``openai-agents``.

    Builds a tool-less structured-output agent and runs it once under a timeout.
    Reuses ``settings.RECOMMENDER_MODEL`` / ``RECOMMENDER_AGENT_TIMEOUT_SECONDS``
    (no dedicated config keys yet). A timeout or SDK failure is surfaced as
    :class:`BotSummaryUnavailableError` so the caller leaves the narrative absent.
    """

    def build_prompt(self, stats: SessionSummaryStats) -> str:
        return build_bot_summary_prompt(stats)

    def summarize(self, stats: SessionSummaryStats) -> BotSummaryOutput:
        prompt = self.build_prompt(stats)
        return asyncio.run(self._run(prompt))

    async def _run(self, prompt: str) -> BotSummaryOutput:
        agent = build_agent(
            name=_AGENT_NAME,
            instructions=_AGENT_INSTRUCTIONS,
            output_type=BotSummaryOutput,
        )
        timeout = settings.RECOMMENDER_AGENT_TIMEOUT_SECONDS
        try:
            result = await asyncio.wait_for(
                Runner.run(
                    agent, prompt, max_turns=1, run_config=run_config_for_trace()
                ),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise BotSummaryUnavailableError(
                f"The session summary timed out after {timeout}s."
            ) from exc
        except Exception as exc:
            raise BotSummaryUnavailableError(
                f"The session summary could not be generated: {exc}"
            ) from exc
        output: BotSummaryOutput = result.final_output
        return output


def get_bot_summary_model() -> str | None:
    """Return the model id used for summaries (for persisting on the row)."""
    return settings.RECOMMENDER_MODEL
