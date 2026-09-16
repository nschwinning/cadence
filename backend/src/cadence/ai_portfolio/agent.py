"""AI agents for portfolio building and rebalancing, and their output contracts.

Ported from trading-bot's ``ai_portfolio_agent`` and adapted to Cadence:

- The agents are built with Cadence's :func:`cadence.agents.build_agent` (which
  forces a Pydantic ``output_type``) and its SerpAPI ``web_search`` tool, on
  :data:`settings.AI_PORTFOLIO_MODEL`.
- The public entrypoints (:func:`build_ai_portfolio` / :func:`rebalance_ai_portfolio`)
  are **synchronous**, wrapping ``asyncio.run(Runner.run(...))`` under a timeout —
  the same sync-over-async pattern the recommender agent uses so the background
  job runner stays fully synchronous. :class:`AIPortfolioAgent` is the seam service
  code depends on, so tests can inject a fake with no network.

Both flows are **long-only** and operate over the entire asset universe as the
candidate set. The agent may additionally discover a bounded number of assets
beyond the universe. Cost is bounded by three caps
(:data:`settings.AI_PORTFOLIO_MAX_TURNS`, ``AI_PORTFOLIO_MAX_WEB_SEARCHES``,
``AI_PORTFOLIO_MAX_NEW_ASSETS``): the turn cap is enforced by the SDK, the
web-search cap by the ``web_search`` tool's per-run budget, and the discovery cap
by the service when it adds newly-proposed tickers to the universe.
"""

from __future__ import annotations

import asyncio
import json
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from agents.run import Runner
from pydantic import BaseModel, Field

from cadence.agents import build_agent
from cadence.agents.tools import web_search, web_search_budget
from cadence.config import settings

BUILD_TIMEOUT_SECONDS = 300
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


def _builder_instructions() -> str:
    return f"""
You are a seasoned investment portfolio manager building a long-term buy-and-hold portfolio.
Select stocks from the provided candidate universe for a diversified, LONG-ONLY portfolio.
Use the web_search tool to research current market conditions and recent news.

Requirements:
- Select stocks with strong long-term fundamentals (2-5 year horizon)
- Diversify across sectors where possible
- All positions are LONG (buy-and-hold); never propose short positions
- allocation_pct values across ALL picks must sum to approximately 1.0
- You may set an asset's allocation_pct to ~0 to effectively exclude it
- Provide concrete, evidence-based investment theses
- Focus on stocks you have high conviction in
- Candidates may include crypto assets (shown via their ``category``); crypto uses
  yfinance-style tickers like ``BTC-USD`` and trades 24/7. Size any crypto weight
  according to the requested risk profile.

Discovery and cost controls:
- You may also research and include assets NOT in the candidate universe if you
  find compelling opportunities; clearly explain why each merits inclusion.
- You may discover at most {settings.AI_PORTFOLIO_MAX_NEW_ASSETS} assets beyond the universe.
- Perform at most {settings.AI_PORTFOLIO_MAX_WEB_SEARCHES} web searches total across this task; batch your research.
"""


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


def _build_portfolio_input(
    candidates: list[dict[str, Any]],
    risk_profile: str,
) -> str:
    candidates_json = json.dumps(candidates, indent=2)
    return f"""
Build a {risk_profile} long-only buy-and-hold portfolio allocating over the candidate universe below.
You may also discover a bounded number of assets beyond this list.
allocation_pct values across all picks must sum to approximately 1.0.

Candidate universe (JSON):
{candidates_json}
"""


def _build_rebalance_input(
    input_template: str,
    holdings: list[dict[str, Any]],
    account_summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    risk_profile: str,
) -> str:
    """Render the versioned rebalance ``input_template`` with the run's values."""
    return _render(
        input_template,
        risk_profile=risk_profile,
        holdings_json=json.dumps(holdings, indent=2),
        account_json=json.dumps(account_summary, indent=2),
        candidates_json=json.dumps(candidates, indent=2),
    )


# --------------------------------------------------------------------------- #
# Sync entrypoints (sync-over-async: asyncio.run(Runner.run(...)) + timeout)
# --------------------------------------------------------------------------- #


def build_ai_portfolio(
    candidates: list[dict[str, Any]],
    risk_profile: str = "balanced",
) -> AIPortfolioBuildResult:
    """Run the builder agent and return its validated :class:`AIPortfolioBuildResult`."""
    return asyncio.run(_run_build(candidates=candidates, risk_profile=risk_profile))


async def _run_build(
    candidates: list[dict[str, Any]],
    risk_profile: str,
) -> AIPortfolioBuildResult:
    agent = build_agent(
        name="AIPortfolioBuilderAgent",
        instructions=_builder_instructions(),
        output_type=AIPortfolioBuildResult,
        tools=[web_search],
        model=settings.AI_PORTFOLIO_MODEL,
    )

    with web_search_budget(settings.AI_PORTFOLIO_MAX_WEB_SEARCHES):
        result = await asyncio.wait_for(
            Runner.run(
                agent,
                _build_portfolio_input(candidates, risk_profile),
                max_turns=settings.AI_PORTFOLIO_MAX_TURNS,
            ),
            timeout=BUILD_TIMEOUT_SECONDS,
        )
    output: AIPortfolioBuildResult = result.final_output
    return output


def rebalance_ai_portfolio(
    holdings: list[dict[str, Any]],
    account_summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    risk_profile: str,
    instructions: str,
    input_template: str,
) -> AIRebalanceResult:
    """Run the rebalance agent and return its validated :class:`AIRebalanceResult`.

    ``instructions`` and ``input_template`` are the active versioned prompt loaded
    from the database by the caller; both may carry ``{name}`` placeholders that
    are filled here (the reasoning/discovery caps on the instructions; the run
    values on the input template).
    """
    return asyncio.run(
        _run_rebalance(
            holdings=holdings,
            account_summary=account_summary,
            candidates=candidates,
            risk_profile=risk_profile,
            instructions=instructions,
            input_template=input_template,
        )
    )


async def _run_rebalance(
    holdings: list[dict[str, Any]],
    account_summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    risk_profile: str,
    instructions: str,
    input_template: str,
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
        model=settings.AI_PORTFOLIO_MODEL,
    )

    with web_search_budget(settings.AI_PORTFOLIO_MAX_WEB_SEARCHES):
        result = await asyncio.wait_for(
            Runner.run(
                agent,
                _build_rebalance_input(
                    input_template, holdings, account_summary, candidates, risk_profile
                ),
                max_turns=settings.AI_PORTFOLIO_MAX_TURNS,
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
    """Seam for building and rebalancing AI portfolios.

    Implemented by :class:`OpenAIAIPortfolioAgent` in production and by a fake in
    tests. Both methods are synchronous so the background job runner stays fully
    sync; the real implementation drives the async SDK internally.
    """

    def build(
        self,
        candidates: list[dict[str, Any]],
        risk_profile: str,
    ) -> AIPortfolioBuildResult:
        """Return a structured portfolio the agent built from the candidates."""
        ...

    def rebalance(
        self,
        holdings: list[dict[str, Any]],
        account_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        risk_profile: str,
        instructions: str,
        input_template: str,
    ) -> AIRebalanceResult:
        """Return the agent's structured rebalance target weights.

        ``instructions``/``input_template`` are the active versioned prompt the
        caller loaded from the database (both may carry ``{name}`` placeholders).
        """
        ...


class OpenAIAIPortfolioAgent:
    """Production :class:`AIPortfolioAgent` backed by ``openai-agents``."""

    def build(
        self,
        candidates: list[dict[str, Any]],
        risk_profile: str,
    ) -> AIPortfolioBuildResult:
        return build_ai_portfolio(candidates=candidates, risk_profile=risk_profile)

    def rebalance(
        self,
        holdings: list[dict[str, Any]],
        account_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        risk_profile: str,
        instructions: str,
        input_template: str,
    ) -> AIRebalanceResult:
        return rebalance_ai_portfolio(
            holdings=holdings,
            account_summary=account_summary,
            candidates=candidates,
            risk_profile=risk_profile,
            instructions=instructions,
            input_template=input_template,
        )
