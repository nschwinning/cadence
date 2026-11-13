"""AI agent for portfolio rebalancing, and its output contracts.

Ported from trading-bot's ``ai_portfolio_agent`` and adapted to Cadence:

- The agent is built with Cadence's :func:`cadence.agents.build_agent` (which
  forces a Pydantic ``output_type``) and its SerpAPI ``web_search`` tool, on
  :data:`settings.AI_PORTFOLIO_MODEL`.
- The public entrypoint (:func:`rebalance_ai_portfolio`) is **synchronous**,
  wrapping ``asyncio.run(Runner.run(...))`` under a timeout — the same
  sync-over-async pattern the recommender agent uses so the background job runner
  stays fully synchronous. :class:`AIPortfolioAgent` is the seam service code
  depends on, so tests can inject a fake with no network.

The rebalance flow is **long-only** and operates over the entire asset universe
as the candidate set (a session's opening allocation runs as its first rebalance,
see ``flows/build.py``). The agent may additionally discover a bounded number of
assets beyond the universe. Cost is bounded by three caps
(:data:`settings.AI_PORTFOLIO_MAX_TURNS`, ``AI_PORTFOLIO_MAX_WEB_SEARCHES``,
``AI_PORTFOLIO_MAX_NEW_ASSETS``): the turn cap is enforced by the SDK, the
web-search cap by the ``web_search`` tool's per-run budget, and the discovery cap
by the service when it adds newly-proposed tickers to the universe.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from agents.run import Runner
from pydantic import BaseModel, Field

from cadence.agents import build_agent, run_config_for_trace
from cadence.agents.tools import web_search, web_search_budget
from cadence.config import settings

REBALANCE_TIMEOUT_SECONDS = 300


# --------------------------------------------------------------------------- #
# Structured output models
# --------------------------------------------------------------------------- #


class PositionSide(str, Enum):
    """Retained for compatibility; the AI flows are long-only and only use LONG."""

    LONG = "long"
    SHORT = "short"


class AIPortfolioStock(BaseModel):
    ticker: str = Field(description="Stock ticker symbol")
    company_name: str = Field(description="Company name")
    side: PositionSide = Field(
        default=PositionSide.LONG, description="Always long (buy-and-hold)"
    )
    allocation_pct: float = Field(
        ge=0.0, le=1.0, description="Fraction of total capital (0.0-1.0)"
    )
    investment_thesis: str = Field(description="Why this stock should be in the portfolio")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this pick")


class AIPortfolioBuildResult(BaseModel):
    portfolio_name: str = Field(description="A descriptive name for the portfolio")
    stocks: list[AIPortfolioStock] = Field(description="Stocks for the portfolio")
    overall_thesis: str = Field(description="Overall investment thesis for this portfolio")
    risk_assessment: str = Field(description="Key risks for the portfolio as a whole")


class AITargetAllocation(BaseModel):
    """A desired end-state target weight for one ticker after a rebalance."""

    ticker: str = Field(description="Stock ticker symbol")
    company_name: str = Field(description="Company name")
    allocation_pct: float = Field(
        ge=0.0, le=1.0, description="Desired fraction of total capital (0.0-1.0)"
    )
    investment_thesis: str = Field(description="Why this target weight is appropriate")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this target")


class AIRebalanceResult(BaseModel):
    """The agent's desired end-state target weights across the universe."""

    evaluation_summary: str = Field(
        description="Overall market assessment and portfolio evaluation"
    )
    target_allocations: list[AITargetAllocation] = Field(
        default_factory=list,
        description=(
            "Desired end-state target weights. Tickers absent (or at ~0 weight) "
            "are to be exited. Weights should sum to approximately 1.0."
        ),
    )
    portfolio_health: str = Field(
        description=(
            "Overall portfolio health assessment: healthy, needs_adjustment, "
            "or significant_changes_needed"
        )
    )


# --------------------------------------------------------------------------- #
# Instructions and prompt builders
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GuardrailInstruction:
    """Advisory guardrail caps told to the AI so it can plan within them.

    These are advisory only: the deterministic clamp in the executor is the actual
    guarantee. When guardrails are disabled the caller passes ``None`` and no
    guardrail text is added to the prompt.
    """

    max_per_asset: float
    max_per_class: float
    min_positions: int
    max_invested: float


def _guardrails_block(guardrails: GuardrailInstruction) -> str:
    """Render the advisory guardrail caps appended to a build/rebalance prompt."""
    return (
        "\nRisk guardrails (plan within these; they are enforced deterministically "
        "after you respond):\n"
        f"- Maximum per single asset: {guardrails.max_per_asset:.0%} of capital\n"
        f"- Maximum per asset class: {guardrails.max_per_class:.0%} of capital\n"
        f"- Minimum number of positions: {guardrails.min_positions}\n"
        "- Maximum invested (remainder held as cash): "
        f"{guardrails.max_invested:.0%} of capital\n"
    )


def _render(template: str, **values: str) -> str:
    """Fill ``{name}`` placeholders in ``template`` by explicit token replacement.

    Deliberately not ``str.format``: the rebalance input embeds JSON blobs and a
    prompt version may contain literal ``{``/``}``; explicit replacement is
    brace-safe and only touches the known keys. The rebalance instructions and
    input templates are stored versioned in the database (see
    :class:`cadence.ai_portfolio.models.RebalancePrompt`); this renders them with
    the run's values exactly as the previous hardcoded f-strings did.
    """
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _summarize_recent_outcomes(
    recent_outcomes: list[dict[str, Any]],
) -> str | None:
    """Distill recent daily-run snapshots into a compact, cost-forward summary.

    Each entry is ``{"run_date": <iso str | None>, "document": <daily-run document>}``
    and the caller passes them most-recent-first. Each day renders to one line that
    leads with **net-of-fees** realized P&L (the run's gross ``realized_pnl`` minus the
    day's ``fees_total``) and the **fees paid**, then the order count and the
    end-of-day valuation/return, plus a gate-drop count when present — the agent's
    known failure mode is churn whose fees erode returns, so cost leads.

    Reads everything defensively with ``.get(...)`` because the document schema has
    evolved over time: a missing field is simply omitted (a missing ``fees_total``
    reads as 0, so net equals gross), and an entry that yields nothing contributes no
    line. Returns ``None`` when there is nothing to show so the caller omits the
    section entirely (keeping the prompt byte-identical).
    """
    lines: list[str] = []
    for entry in recent_outcomes:
        document = entry.get("document")
        if not isinstance(document, dict):
            continue
        run = document.get("run")
        run_stats = run.get("run_stats") if isinstance(run, dict) else None
        run_stats = run_stats if isinstance(run_stats, dict) else {}
        valuation = document.get("valuation")
        valuation = valuation if isinstance(valuation, dict) else {}

        realized = run_stats.get("realized_pnl")
        fees_raw = document.get("fees_total")
        fees = float(fees_raw) if isinstance(fees_raw, (int, float)) else 0.0
        orders_count = document.get("orders_count")
        total_value = valuation.get("total_value")
        daily_pnl_pct = valuation.get("daily_pnl_pct")
        gate = run_stats.get("gate")
        dropped = gate.get("dropped") if isinstance(gate, dict) else None

        parts: list[str] = []
        if isinstance(realized, (int, float)):
            parts.append(f"net realized P&L {_signed_money(float(realized) - fees)}")
        parts.append(f"fees {_money(fees)}")
        if isinstance(orders_count, int):
            parts.append(f"{orders_count} orders")
        if isinstance(total_value, (int, float)):
            value_part = f"end value {_money(float(total_value))}"
            if isinstance(daily_pnl_pct, (int, float)):
                value_part += f" ({float(daily_pnl_pct) * 100:+.2f}%)"
            parts.append(value_part)
        if isinstance(dropped, int) and dropped > 0:
            parts.append(f"{dropped} candidates gated out")

        if not parts:
            continue
        date_label = entry.get("run_date") or "recent"
        lines.append(f"- {date_label}: " + "; ".join(parts))

    if not lines:
        return None
    return "\n".join(lines)


def _money(value: float) -> str:
    """Format a dollar amount, e.g. ``$1,234.56``."""
    return f"${value:,.2f}"


def _signed_money(value: float) -> str:
    """Format a signed dollar amount, e.g. ``+$12.34`` / ``-$5.00``."""
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.2f}"


def _recent_outcomes_block(summary: str) -> str:
    """Wrap the distilled per-day summary in its advisory prompt section."""
    return (
        "Recent run outcomes (advisory — your own recent daily results, most recent "
        "first). Use these to avoid churn whose transaction fees erode returns; they "
        "add no hard constraints:\n"
        f"{summary}"
    )


def _run_context_block(run_date: date) -> str:
    """Today's date and recency-aware research guidance, appended to every run.

    Added to every rebalance input whatever the session's frozen prompt version
    (like the guardrails and recent-outcomes sections), so every portfolio researches
    with the current date in mind and sees the per-ticker ``recent_headlines``.
    """
    return (
        f"\n## Run context\n"
        f"Today is {run_date.isoformat()} (US/Eastern).\n"
        "Research guidance: before keeping or adding a name, check for material "
        "developments of the last 7 days (management changes, investigations, "
        "guidance changes, mergers). Put the current month and year in news searches "
        "and prefer the `top_stories` block of search results. Check each result's "
        "date and disregard results older than the period you are assessing; company "
        "fiscal years differ from calendar years (a 'fiscal 2026' quarter may have "
        "ended in 2025). Each holding and candidate may carry `recent_headlines` — the "
        "newest news headlines about it, with their publication times.\n"
    )


def _build_rebalance_input(
    input_template: str,
    holdings: list[dict[str, Any]],
    account_summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    risk_profile: str,
    guardrails: GuardrailInstruction | None = None,
    recent_outcomes: list[dict[str, Any]] | None = None,
    run_date: date | None = None,
) -> str:
    """Render the versioned rebalance ``input_template`` with the run's values.

    When guardrails are enabled the advisory caps block is appended after the
    rendered template so the AI can plan within the frozen caps. When
    ``recent_outcomes`` are supplied and distill to a non-empty summary, an advisory
    "Recent run outcomes" section is appended; otherwise the prompt is byte-identical
    to the no-feedback case.
    """
    rendered = _render(
        input_template,
        risk_profile=risk_profile,
        holdings_json=json.dumps(holdings, indent=2),
        account_json=json.dumps(account_summary, indent=2),
        candidates_json=json.dumps(candidates, indent=2),
    )
    if guardrails:
        rendered = f"{rendered}\n{_guardrails_block(guardrails)}"
    if recent_outcomes:
        summary = _summarize_recent_outcomes(recent_outcomes)
        if summary:
            rendered = f"{rendered}\n{_recent_outcomes_block(summary)}"
    if run_date is not None:
        rendered = f"{rendered}\n{_run_context_block(run_date)}"
    return rendered


# --------------------------------------------------------------------------- #
# Sync entrypoints (sync-over-async: asyncio.run(Runner.run(...)) + timeout)
# --------------------------------------------------------------------------- #


def rebalance_ai_portfolio(
    holdings: list[dict[str, Any]],
    account_summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    risk_profile: str,
    instructions: str,
    input_template: str,
    guardrails: GuardrailInstruction | None = None,
    recent_outcomes: list[dict[str, Any]] | None = None,
    model: str | None = None,
    run_date: date | None = None,
) -> AIRebalanceResult:
    """Run the rebalance agent and return its validated :class:`AIRebalanceResult`.

    ``instructions`` and ``input_template`` are the active versioned prompt loaded
    from the database by the caller; both may carry ``{name}`` placeholders that
    are filled here (the reasoning/discovery caps on the instructions; the run
    values on the input template). ``guardrails`` (when set) appends the advisory
    cap block to the rendered input. ``recent_outcomes`` (when set) appends the
    advisory "Recent run outcomes" section distilled from the session's recent
    daily-run snapshots. ``model`` (when set) is the session's frozen AI model the
    run executes on; absent, it falls back to :data:`settings.AI_PORTFOLIO_MODEL`.
    """
    return asyncio.run(
        _run_rebalance(
            holdings=holdings,
            account_summary=account_summary,
            candidates=candidates,
            risk_profile=risk_profile,
            instructions=instructions,
            input_template=input_template,
            guardrails=guardrails,
            recent_outcomes=recent_outcomes,
            model=model,
            run_date=run_date,
        )
    )


async def _run_rebalance(
    holdings: list[dict[str, Any]],
    account_summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    risk_profile: str,
    instructions: str,
    input_template: str,
    guardrails: GuardrailInstruction | None = None,
    recent_outcomes: list[dict[str, Any]] | None = None,
    model: str | None = None,
    run_date: date | None = None,
) -> AIRebalanceResult:
    agent = build_agent(
        name="AIRebalanceEvaluatorAgent",
        instructions=_render(
            instructions,
            max_new_assets=str(settings.AI_PORTFOLIO_MAX_NEW_ASSETS),
            max_web_searches=str(settings.AI_PORTFOLIO_MAX_WEB_SEARCHES),
        ),
        output_type=AIRebalanceResult,
        tools=[web_search],
        model=model or settings.AI_PORTFOLIO_MODEL,
    )

    with web_search_budget(settings.AI_PORTFOLIO_MAX_WEB_SEARCHES):
        result = await asyncio.wait_for(
            Runner.run(
                agent,
                _build_rebalance_input(
                    input_template,
                    holdings,
                    account_summary,
                    candidates,
                    risk_profile,
                    guardrails,
                    recent_outcomes,
                    run_date,
                ),
                max_turns=settings.AI_PORTFOLIO_MAX_TURNS,
                run_config=run_config_for_trace(),
            ),
            timeout=REBALANCE_TIMEOUT_SECONDS,
        )
    output: AIRebalanceResult = result.final_output
    return output


# --------------------------------------------------------------------------- #
# Seam for service/DI (production impl + Protocol) so tests can swap a fake
# --------------------------------------------------------------------------- #


@runtime_checkable
class AIPortfolioAgent(Protocol):
    """Seam for rebalancing AI portfolios.

    Implemented by :class:`OpenAIAIPortfolioAgent` in production and by a fake in
    tests. The method is synchronous so the background job runner stays fully sync;
    the real implementation drives the async SDK internally.
    """

    def rebalance(
        self,
        holdings: list[dict[str, Any]],
        account_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        risk_profile: str,
        instructions: str,
        input_template: str,
        guardrails: GuardrailInstruction | None = None,
        recent_outcomes: list[dict[str, Any]] | None = None,
        model: str | None = None,
        run_date: date | None = None,
    ) -> AIRebalanceResult:
        """Return the agent's structured rebalance target weights.

        ``instructions``/``input_template`` are the active versioned prompt the
        caller loaded from the database (both may carry ``{name}`` placeholders).
        ``guardrails`` (when set) tells the AI the advisory caps to plan within.
        ``recent_outcomes`` (when set) is the session's recent daily-run snapshots,
        distilled into the advisory "Recent run outcomes" prompt section. ``model``
        (when set) is the session's frozen AI model the run executes on; absent, it
        falls back to :data:`settings.AI_PORTFOLIO_MODEL`.
        """
        ...


class OpenAIAIPortfolioAgent:
    """Production :class:`AIPortfolioAgent` backed by ``openai-agents``."""

    def rebalance(
        self,
        holdings: list[dict[str, Any]],
        account_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        risk_profile: str,
        instructions: str,
        input_template: str,
        guardrails: GuardrailInstruction | None = None,
        recent_outcomes: list[dict[str, Any]] | None = None,
        model: str | None = None,
        run_date: date | None = None,
    ) -> AIRebalanceResult:
        return rebalance_ai_portfolio(
            holdings=holdings,
            account_summary=account_summary,
            candidates=candidates,
            risk_profile=risk_profile,
            instructions=instructions,
            input_template=input_template,
            guardrails=guardrails,
            recent_outcomes=recent_outcomes,
            model=model,
            run_date=run_date,
        )
