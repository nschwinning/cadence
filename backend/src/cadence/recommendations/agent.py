"""The asset-recommender agent and its structured contract.

The agent is asked for candidate tickers that already look eligible under
Cadence's rules (so eligibility goes into the prompt), using a SerpAPI
``web_search`` tool. Its output is a Pydantic :class:`RecommendationOutput`;
:class:`RecommenderAgent` is the seam service code depends on so tests can swap
in a fake with no network.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from agents.items import ToolCallItem
from agents.run import Runner
from pydantic import BaseModel, Field

from cadence.agents import build_agent
from cadence.agents.tools import web_search
from cadence.assets import constants as asset_constants
from cadence.config import settings
from cadence.recommendations.composition import UniverseComposition
from cadence.recommendations.constants import RunTarget
from cadence.recommendations.errors import RecommendationAgentError

_AGENT_NAME = "AssetRecommenderAgent"

_AGENT_INSTRUCTIONS = """
You are an investment universe researcher for a European (EUR) investor.
Your job is to propose real, currently-listed assets that plausibly satisfy a
fixed set of eligibility rules. Use the web_search tool to check recent facts
(price, market capitalization, liquidity, listing history) before proposing an
asset. Base your final answer on tool results from this run; if the evidence is
insufficient, return fewer candidates rather than guessing. Only return valid
exchange ticker symbols. Do not invent tickers. Never propose an asset that is
already in the universe: the prompt lists the tickers to exclude, and any such
proposal is wasted because it will be rejected as a duplicate.
""".strip()

_WATCHLIST_AGENT_INSTRUCTIONS = """
You are an emerging-companies scout for a European (EUR) investor's watchlist.
Your job is to propose real, currently-listed US companies that are EMERGING —
young, fast-growing names from promising sectors that are NOT yet mature enough
for a conservative tradable universe (they may have a short listing history or a
smaller market capitalization). Use the web_search tool to check recent facts
before proposing a company. Base your final answer on tool results from this run;
if the evidence is insufficient, return fewer candidates rather than guessing.
Only return valid US exchange ticker symbols for companies (common stock), never
ETFs, funds, or crypto. Do not invent tickers. Never propose a ticker that is
already tracked: the prompt lists the tickers to exclude, and any such proposal
is wasted because it will be rejected as a duplicate.
""".strip()


def _agent_instructions(target: RunTarget) -> str:
    """Return the system instructions for the run's target."""
    return (
        _WATCHLIST_AGENT_INSTRUCTIONS
        if target == RunTarget.WATCHLIST
        else _AGENT_INSTRUCTIONS
    )


@dataclass(frozen=True)
class EligibilityCriteria:
    """The USD eligibility thresholds shown to the agent in the prompt.

    Mirrors :mod:`cadence.assets.constants`; kept as an explicit value object so
    it is an argument to :meth:`RecommenderAgent.recommend` (and thus assertable
    in tests) rather than a hidden import inside the prompt builder.
    """

    min_price_usd: float
    min_avg_daily_turnover_usd: float
    min_market_cap_usd: float
    min_history_years: float


def default_eligibility_criteria() -> EligibilityCriteria:
    """Build the criteria from the assets domain's fixed thresholds."""
    return EligibilityCriteria(
        min_price_usd=asset_constants.MIN_PRICE_USD,
        min_avg_daily_turnover_usd=asset_constants.MIN_AVG_DAILY_TURNOVER_USD,
        min_market_cap_usd=asset_constants.MIN_MARKET_CAP_USD,
        min_history_years=asset_constants.MIN_HISTORY_YEARS,
    )


class RecommendationCandidate(BaseModel):
    """A single proposed asset: its ticker and why the agent picked it."""

    ticker: str = Field(description="Exchange ticker symbol, e.g. AAPL or SAP.DE")
    rationale: str = Field(
        description="Brief reason this asset was proposed and looks eligible"
    )


class RecommendationOutput(BaseModel):
    """The agent's structured output: a list of candidate assets."""

    candidates: list[RecommendationCandidate] = Field(
        default_factory=list,
        description="Proposed assets that plausibly meet the eligibility rules",
    )


@dataclass(frozen=True)
class RecommendationResult:
    """What :meth:`RecommenderAgent.recommend` returns.

    Carries the validated agent output plus how many tool calls the agent made,
    both of which the service persists on the run row.
    """

    output: RecommendationOutput
    tool_call_count: int


@runtime_checkable
class RecommenderAgent(Protocol):
    """Seam for producing asset recommendations.

    Implemented by :class:`OpenAIRecommenderAgent` in production and by a fake in
    tests. ``recommend`` is synchronous so the background executor stays fully
    sync; the real implementation drives the async SDK internally.
    """

    def recommend(
        self,
        categories: list[str],
        count: int,
        criteria: EligibilityCriteria,
        composition: UniverseComposition,
        exclude_tickers: list[str],
        target: RunTarget = RunTarget.UNIVERSE,
    ) -> RecommendationResult:
        """Return up to ``count``-worth of candidates for the given categories.

        ``exclude_tickers`` are already tracked as assets and MUST NOT be
        proposed. ``target`` selects the universe (default) or the
        emerging-companies watchlist prompt.
        """
        ...

    def build_prompt(
        self,
        categories: list[str],
        count: int,
        criteria: EligibilityCriteria,
        composition: UniverseComposition,
        exclude_tickers: list[str],
        target: RunTarget = RunTarget.UNIVERSE,
    ) -> str:
        """Return the exact prompt text that would be sent for this request."""
        ...


def _render_composition(composition: UniverseComposition) -> str:
    """Render the current-universe composition and the diversification steer.

    Sectors list every economic sector (absent ones shown as ``0``) so the agent
    can concretely target the gaps; countries list only those present.
    """
    if composition.is_empty:
        return (
            "The universe is currently empty, so any well-diversified set of "
            "eligible assets is welcome."
        )
    sector_line = ", ".join(f"{e.key} {e.count}" for e in composition.sectors)
    country_line = ", ".join(f"{e.key} {e.count}" for e in composition.countries)
    return f"""
The universe currently holds {composition.total} assets. Current composition —
  By sector: {sector_line}
  By country: {country_line}
To improve diversification, PREFER candidates from under-represented or absent
sectors and countries, and AVOID adding to the largest existing groups.
""".strip()


def _render_exclusions(exclude_tickers: list[str]) -> str:
    """Render the do-not-propose list of tickers already in the universe.

    Existing tickers would be caught as duplicates server-side, so listing them
    up front stops the agent wasting proposals (and web searches) on names that
    can never be added.
    """
    if not exclude_tickers:
        return (
            "The universe is currently empty, so no tickers are excluded — "
            "propose any eligible assets."
        )
    ticker_line = ", ".join(exclude_tickers)
    return f"""
These {len(exclude_tickers)} tickers are already in the universe. Do NOT propose
any of them (proposing one is wasted — it will be rejected as a duplicate):
  {ticker_line}
""".strip()


def build_recommendation_prompt(
    categories: list[str],
    count: int,
    criteria: EligibilityCriteria,
    composition: UniverseComposition,
    exclude_tickers: list[str],
) -> str:
    """Compose the agent input from the requested categories and thresholds.

    The eligibility thresholds are stated up front so the agent screens for them
    while searching; Cadence still re-validates every candidate server-side. The
    current-universe composition is included so the agent can steer toward
    under-represented sectors and countries — a soft preference only; it does not
    relax eligibility or de-duplication. ``exclude_tickers`` are the assets
    already in the universe; the agent is told not to propose any of them.
    """
    category_line = ", ".join(categories) if categories else "any"
    return f"""
Find up to {count} distinct assets for a EUR investor's universe.

Restrict candidates to these categories: {category_line}.

{_render_exclusions(exclude_tickers)}

{_render_composition(composition)}

Prefer constituents of major stock indices (STOXX Europe 600, DAX, S&P 500,
Dow Jones Industrial Average, and comparable large-cap indices). Use web_search
to confirm current index membership; eligible names that are not index
constituents are still welcome when they improve diversification.

Each asset must plausibly satisfy ALL of these eligibility rules (all monetary
values in USD, converted from the asset's native currency):
- Latest price greater than {criteria.min_price_usd:,.0f} USD.
- Average daily turnover at least {criteria.min_avg_daily_turnover_usd:,.0f} USD.
- Market capitalization greater than {criteria.min_market_cap_usd:,.0f} USD.
- At least {criteria.min_history_years:,.0f} years of price history.

Use web_search to verify these facts before proposing an asset. Prefer well
known, liquid, currently-listed instruments. Return only valid ticker symbols
with a one-line rationale each. If you cannot verify enough assets, return
fewer rather than guessing.
""".strip()


def build_watchlist_recommendation_prompt(
    categories: list[str],
    count: int,
    criteria: EligibilityCriteria,
    composition: UniverseComposition,
    exclude_tickers: list[str],
) -> str:
    """Compose the watchlist (emerging-companies) agent input.

    Unlike the universe prompt, this explicitly seeks EMERGING US companies from
    promising sectors and deliberately RELAXES the maturity thresholds (history,
    market capitalization) — young, growing names are the point. It keeps the hard
    executability floor (a real, currently-listed, brokerage-tradable US common
    stock) and the all-assets exclusion list. ``criteria`` is shown only as the
    universe bar these companies need not yet clear, so the agent understands what
    "not yet mature" means. ``composition`` is unused here (the watchlist is not
    diversified against the universe) but kept in the signature for symmetry.
    """
    _ = composition  # watchlist scouting is not steered by universe composition
    category_line = ", ".join(categories) if categories else "stock"
    return f"""
Find up to {count} distinct EMERGING US companies for an investor's watchlist.

Restrict candidates to these categories: {category_line}. Only US-listed common
stock — no ETFs, funds, or crypto.

{_render_exclusions(exclude_tickers)}

Seek young, fast-growing companies from PROMISING SECTORS (for example AI,
semiconductors, clean energy, biotech, fintech, space, robotics) that are NOT yet
mature enough for a conservative tradable universe. It is EXPECTED and WELCOME
that these names do not yet clear the mature-universe bar below — admitting
emerging, not-yet-eligible companies is the entire purpose of the watchlist:
- Latest price greater than {criteria.min_price_usd:,.0f} USD.
- Average daily turnover at least {criteria.min_avg_daily_turnover_usd:,.0f} USD.
- Market capitalization greater than {criteria.min_market_cap_usd:,.0f} USD.
- At least {criteria.min_history_years:,.0f} years of price history.

Do NOT screen candidates out merely for missing those maturity thresholds. The
only hard requirement is that each candidate is a real, currently-listed US
common stock that a US brokerage can trade. Use web_search to confirm the company
is genuinely listed and tradable before proposing it. Return only valid US ticker
symbols with a one-line rationale each. If you cannot verify enough companies,
return fewer rather than guessing.
""".strip()


def build_prompt_for_target(
    categories: list[str],
    count: int,
    criteria: EligibilityCriteria,
    composition: UniverseComposition,
    exclude_tickers: list[str],
    target: RunTarget,
) -> str:
    """Dispatch to the universe or watchlist prompt builder for ``target``."""
    builder = (
        build_watchlist_recommendation_prompt
        if target == RunTarget.WATCHLIST
        else build_recommendation_prompt
    )
    return builder(categories, count, criteria, composition, exclude_tickers)


class OpenAIRecommenderAgent:
    """Production :class:`RecommenderAgent` backed by ``openai-agents``.

    Builds a structured-output agent with the ``web_search`` tool, runs it under
    a timeout, and reports the tool-call count from the run.
    """

    def build_prompt(
        self,
        categories: list[str],
        count: int,
        criteria: EligibilityCriteria,
        composition: UniverseComposition,
        exclude_tickers: list[str],
        target: RunTarget = RunTarget.UNIVERSE,
    ) -> str:
        return build_prompt_for_target(
            categories, count, criteria, composition, exclude_tickers, target
        )

    def recommend(
        self,
        categories: list[str],
        count: int,
        criteria: EligibilityCriteria,
        composition: UniverseComposition,
        exclude_tickers: list[str],
        target: RunTarget = RunTarget.UNIVERSE,
    ) -> RecommendationResult:
        prompt = self.build_prompt(
            categories, count, criteria, composition, exclude_tickers, target
        )
        return asyncio.run(self._run(prompt, target))

    async def _run(self, prompt: str, target: RunTarget) -> RecommendationResult:
        agent = build_agent(
            name=_AGENT_NAME,
            instructions=_agent_instructions(target),
            output_type=RecommendationOutput,
            tools=[web_search],
        )
        timeout = settings.RECOMMENDER_AGENT_TIMEOUT_SECONDS
        try:
            result = await asyncio.wait_for(
                Runner.run(agent, prompt, max_turns=settings.RECOMMENDER_MAX_TURNS),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise RecommendationAgentError(
                f"The recommender timed out after {timeout}s while researching "
                "candidates. Try requesting fewer assets, or raise "
                "RECOMMENDER_AGENT_TIMEOUT_SECONDS."
            ) from exc
        output: RecommendationOutput = result.final_output
        tool_call_count = sum(
            1 for item in result.new_items if isinstance(item, ToolCallItem)
        )
        return RecommendationResult(output=output, tool_call_count=tool_call_count)
