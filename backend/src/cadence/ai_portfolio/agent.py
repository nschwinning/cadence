"""AI agents for portfolio building and rebalancing, and their output contracts.

Ported faithfully from trading-bot's ``ai_portfolio_agent`` and its structured
Pydantic output models. Two adaptations to Cadence conventions:

- The agents are built with Cadence's :func:`cadence.agents.build_agent` (which
  forces a Pydantic ``output_type``) and its SerpAPI ``web_search`` tool, on
  :data:`settings.AI_PORTFOLIO_MODEL`.
- The public entrypoints (:func:`build_ai_portfolio` / :func:`rebalance_ai_portfolio`)
  are **synchronous**, wrapping ``asyncio.run(Runner.run(...))`` under a timeout —
  the same sync-over-async pattern the recommender agent uses so the background
  job runner stays fully synchronous. :class:`AIPortfolioAgent` is the seam service
  code depends on, so tests can inject a fake with no network.
"""

from __future__ import annotations

import asyncio
import json
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from agents.run import Runner
from pydantic import BaseModel, Field

from cadence.agents import build_agent
from cadence.agents.tools import web_search
from cadence.config import settings

BUILD_TIMEOUT_SECONDS = 180
BUILD_DISCOVERY_TIMEOUT_SECONDS = 300
REBALANCE_TIMEOUT_SECONDS = 180

#: Cap on agent turns, bounding tool-call loops.
AGENT_MAX_TURNS = 25


# --------------------------------------------------------------------------- #
# Structured output models (ported verbatim from trading-bot agent/models.py)
# --------------------------------------------------------------------------- #


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class AIPortfolioStock(BaseModel):
    ticker: str = Field(description="Stock ticker symbol")
    company_name: str = Field(description="Company name")
    side: PositionSide = Field(description="long = buy, short = sell short")
    allocation_pct: float = Field(
        ge=0.05, le=0.5, description="Fraction of total capital (0.05-0.50)"
    )
    investment_thesis: str = Field(description="Why this stock should be in the portfolio")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this pick")


class AIPortfolioBuildResult(BaseModel):
    portfolio_name: str = Field(description="A descriptive name for the portfolio")
    stocks: list[AIPortfolioStock] = Field(
        min_length=2, max_length=10, description="Stocks for the portfolio"
    )
    overall_thesis: str = Field(description="Overall investment thesis for this portfolio")
    risk_assessment: str = Field(description="Key risks for the portfolio as a whole")


class RebalanceAction(str, Enum):
    HOLD = "hold"
    SELL = "sell"
    COVER = "cover"


class ExistingHoldingEvaluation(BaseModel):
    ticker: str = Field(description="Stock ticker symbol")
    action: RebalanceAction = Field(
        description="hold, sell (close long), or cover (close short)"
    )
    reasoning: str = Field(description="Why to hold, sell, or cover this position")
    confidence: float = Field(ge=0.0, le=1.0)


class NewStockRecommendation(BaseModel):
    ticker: str = Field(description="Stock ticker to add")
    company_name: str = Field(description="Company name")
    side: PositionSide = Field(description="long = buy, short = sell short")
    allocation_pct: float = Field(ge=0.05, le=0.4, description="Fraction of total capital")
    investment_thesis: str = Field(description="Why to add this stock")
    confidence: float = Field(ge=0.0, le=1.0)


class AIRebalanceResult(BaseModel):
    evaluation_summary: str = Field(
        description="Overall market assessment and portfolio evaluation"
    )
    existing_holdings: list[ExistingHoldingEvaluation] = Field(
        description="Evaluation of each current holding"
    )
    new_recommendations: list[NewStockRecommendation] = Field(
        default_factory=list, description="New stocks to add (may be empty)"
    )
    portfolio_health: str = Field(
        description=(
            "Overall portfolio health assessment: healthy, needs_adjustment, "
            "or significant_changes_needed"
        )
    )


# --------------------------------------------------------------------------- #
# Instructions and prompt builders (ported verbatim from trading-bot)
# --------------------------------------------------------------------------- #

_BUILDER_BASE_INSTRUCTIONS = """
You are a seasoned investment portfolio manager building a long-term buy-and-hold portfolio.
Select stocks from the provided candidates for a diversified portfolio.
Use the web_search tool to research current market conditions and recent news for each candidate.

Requirements:
- Select stocks with strong long-term fundamentals (2-5 year horizon)
- Diversify across sectors where possible
- allocation_pct values must sum to approximately 1.0
- Provide concrete, evidence-based investment theses
- Focus on stocks you have high conviction in
"""

_BUILDER_DISCOVERY_ADDON = """
You may also search for and include stocks NOT in the candidate list if you find compelling opportunities.
Clearly explain why any newly discovered stock merits inclusion.
"""

_BUILDER_SHORT_ADDON = """
You may include SHORT positions for stocks you are bearish on.
Set side="short" for stocks you expect to decline.
Short positions should be used selectively and with clear reasoning.
"""

_BUILDER_LONG_ONLY_ADDON = """
All positions must be LONG (side="long"). Do not include any short positions.
"""

_REBALANCE_BASE_INSTRUCTIONS = """
You are a portfolio manager reviewing an existing buy-and-hold portfolio.
Analyze each current holding's performance and market outlook, then recommend actions.
Use the web_search tool to check latest news and fundamentals for each holding.

Requirements:
- Evaluate each existing holding and recommend an action with clear reasoning
- For LONG positions: recommend "hold" or "sell" (sell = close the position)
- Only recommend closing a position if there are material negative changes (not just short-term dips)
- You may recommend 0-3 new stocks to ADD (only if capital is freed up or portfolio needs diversification)
- Be conservative with changes — buy-and-hold means holding through normal volatility
"""

_REBALANCE_SHORT_ADDON = """
- For SHORT positions: recommend "hold" or "cover" (cover = buy back to close the short)
- New additions can be long or short (side="long" or side="short")
"""

_REBALANCE_LONG_ONLY_ADDON = """
- New additions must all be long positions (side="long")
"""


def _build_portfolio_input(
    candidates: list[dict[str, Any]],
    risk_profile: str,
    allow_new_picks: bool,
    allow_short: bool,
    max_stock_count: int = 8,
) -> str:
    candidates_json = json.dumps(candidates, indent=2)
    return f"""
Build a {risk_profile} buy-and-hold portfolio selecting up to {max_stock_count} stocks.
{"You may also discover stocks beyond this list." if allow_new_picks else "Select ONLY from the candidates below."}
{"You may include short positions." if allow_short else "All positions must be long."}

Candidate stocks (JSON):
{candidates_json}
"""


def _build_rebalance_input(
    holdings: list[dict[str, Any]],
    account_summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    allow_short: bool,
) -> str:
    holdings_json = json.dumps(holdings, indent=2)
    account_json = json.dumps(account_summary, indent=2)
    candidates_json = json.dumps(candidates, indent=2)
    return f"""
Review this portfolio and recommend actions for each holding.
{"New additions can be long or short." if allow_short else "New additions must be long only."}

Current Holdings:
{holdings_json}

Account Summary:
{account_json}

Available candidates for new additions:
{candidates_json}
"""


# --------------------------------------------------------------------------- #
# Sync entrypoints (sync-over-async: asyncio.run(Runner.run(...)) + timeout)
# --------------------------------------------------------------------------- #


def build_ai_portfolio(
    candidates: list[dict[str, Any]],
    risk_profile: str = "balanced",
    allow_new_picks: bool = False,
    allow_short: bool = False,
    max_stock_count: int = 8,
) -> AIPortfolioBuildResult:
    """Run the builder agent and return its validated :class:`AIPortfolioBuildResult`."""
    return asyncio.run(
        _run_build(
            candidates=candidates,
            risk_profile=risk_profile,
            allow_new_picks=allow_new_picks,
            allow_short=allow_short,
            max_stock_count=max_stock_count,
        )
    )


async def _run_build(
    candidates: list[dict[str, Any]],
    risk_profile: str,
    allow_new_picks: bool,
    allow_short: bool,
    max_stock_count: int,
) -> AIPortfolioBuildResult:
    instructions = _BUILDER_BASE_INSTRUCTIONS
    if allow_new_picks:
        instructions += _BUILDER_DISCOVERY_ADDON
    if allow_short:
        instructions += _BUILDER_SHORT_ADDON
    else:
        instructions += _BUILDER_LONG_ONLY_ADDON

    agent = build_agent(
        name="AIPortfolioBuilderAgent",
        instructions=instructions,
        output_type=AIPortfolioBuildResult,
        tools=[web_search],
        model=settings.AI_PORTFOLIO_MODEL,
    )

    timeout = (
        BUILD_DISCOVERY_TIMEOUT_SECONDS if allow_new_picks else BUILD_TIMEOUT_SECONDS
    )
    result = await asyncio.wait_for(
        Runner.run(
            agent,
            _build_portfolio_input(
                candidates, risk_profile, allow_new_picks, allow_short, max_stock_count
            ),
            max_turns=AGENT_MAX_TURNS,
        ),
        timeout=timeout,
    )
    output: AIPortfolioBuildResult = result.final_output
    return output


def rebalance_ai_portfolio(
    holdings: list[dict[str, Any]],
    account_summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    allow_short: bool = False,
) -> AIRebalanceResult:
    """Run the rebalance agent and return its validated :class:`AIRebalanceResult`."""
    return asyncio.run(
        _run_rebalance(
            holdings=holdings,
            account_summary=account_summary,
            candidates=candidates,
            allow_short=allow_short,
        )
    )


async def _run_rebalance(
    holdings: list[dict[str, Any]],
    account_summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    allow_short: bool,
) -> AIRebalanceResult:
    instructions = _REBALANCE_BASE_INSTRUCTIONS
    if allow_short:
        instructions += _REBALANCE_SHORT_ADDON
    else:
        instructions += _REBALANCE_LONG_ONLY_ADDON

    agent = build_agent(
        name="AIRebalanceEvaluatorAgent",
        instructions=instructions,
        output_type=AIRebalanceResult,
        tools=[web_search],
        model=settings.AI_PORTFOLIO_MODEL,
    )

    result = await asyncio.wait_for(
        Runner.run(
            agent,
            _build_rebalance_input(holdings, account_summary, candidates, allow_short),
            max_turns=AGENT_MAX_TURNS,
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
        allow_new_picks: bool,
        allow_short: bool,
        max_stock_count: int,
    ) -> AIPortfolioBuildResult:
        """Return a structured portfolio the agent built from the candidates."""
        ...

    def rebalance(
        self,
        holdings: list[dict[str, Any]],
        account_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        allow_short: bool,
    ) -> AIRebalanceResult:
        """Return the agent's structured rebalance evaluation."""
        ...


class OpenAIAIPortfolioAgent:
    """Production :class:`AIPortfolioAgent` backed by ``openai-agents``."""

    def build(
        self,
        candidates: list[dict[str, Any]],
        risk_profile: str,
        allow_new_picks: bool,
        allow_short: bool,
        max_stock_count: int,
    ) -> AIPortfolioBuildResult:
        return build_ai_portfolio(
            candidates=candidates,
            risk_profile=risk_profile,
            allow_new_picks=allow_new_picks,
            allow_short=allow_short,
            max_stock_count=max_stock_count,
        )

    def rebalance(
        self,
        holdings: list[dict[str, Any]],
        account_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        allow_short: bool,
    ) -> AIRebalanceResult:
        return rebalance_ai_portfolio(
            holdings=holdings,
            account_summary=account_summary,
            candidates=candidates,
            allow_short=allow_short,
        )
