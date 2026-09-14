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
from cadence.recommendations.composition import UniverseComposition

#: Hard ceiling on the agent's wall-clock runtime (search + reasoning).
AGENT_TIMEOUT_SECONDS = 180

#: Cap on agent turns, bounding tool-call loops.
AGENT_MAX_TURNS = 20

_AGENT_NAME = "AssetRecommenderAgent"

_AGENT_INSTRUCTIONS = """
You are an investment universe researcher for a European (EUR) investor.
Your job is to propose real, currently-listed assets that plausibly satisfy a
fixed set of eligibility rules. Use the web_search tool to check recent facts
(price, market capitalization, liquidity, listing history) before proposing an
asset. Base your final answer on tool results from this run; if the evidence is
insufficient, return fewer candidates rather than guessing. Only return valid
exchange ticker symbols. Do not invent tickers.
""".strip()


@dataclass(frozen=True)
class EligibilityCriteria:
    """The EUR eligibility thresholds shown to the agent in the prompt.

    Mirrors :mod:`cadence.assets.constants`; kept as an explicit value object so
    it is an argument to :meth:`RecommenderAgent.recommend` (and thus assertable
    in tests) rather than a hidden import inside the prompt builder.
    """

    min_price_eur: float
    min_avg_daily_turnover_eur: float
    min_market_cap_eur: float
    min_history_years: float


def default_eligibility_criteria() -> EligibilityCriteria:
    """Build the criteria from the assets domain's fixed thresholds."""
    return EligibilityCriteria(
        min_price_eur=asset_constants.MIN_PRICE_EUR,
        min_avg_daily_turnover_eur=asset_constants.MIN_AVG_DAILY_TURNOVER_EUR,
        min_market_cap_eur=asset_constants.MIN_MARKET_CAP_EUR,
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
    ) -> RecommendationResult:
        """Return up to ``count``-worth of candidates for the given categories."""
        ...

    def build_prompt(
        self,
        categories: list[str],
        count: int,
        criteria: EligibilityCriteria,
        composition: UniverseComposition,
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


def build_recommendation_prompt(
    categories: list[str],
    count: int,
    criteria: EligibilityCriteria,
    composition: UniverseComposition,
) -> str:
    """Compose the agent input from the requested categories and thresholds.

    The eligibility thresholds are stated up front so the agent screens for them
    while searching; Cadence still re-validates every candidate server-side. The
    current-universe composition is included so the agent can steer toward
    under-represented sectors and countries — a soft preference only; it does not
    relax eligibility or de-duplication.
    """
    category_line = ", ".join(categories) if categories else "any"
    return f"""
Find up to {count} distinct assets for a EUR investor's universe.

Restrict candidates to these categories: {category_line}.

{_render_composition(composition)}

Prefer constituents of major stock indices (STOXX Europe 600, DAX, S&P 500,
Dow Jones Industrial Average, and comparable large-cap indices). Use web_search
to confirm current index membership; eligible names that are not index
constituents are still welcome when they improve diversification.

Each asset must plausibly satisfy ALL of these eligibility rules (all monetary
values in EUR, converted from the asset's native currency):
- Latest price greater than {criteria.min_price_eur:,.0f} EUR.
- Average daily turnover at least {criteria.min_avg_daily_turnover_eur:,.0f} EUR.
- Market capitalization greater than {criteria.min_market_cap_eur:,.0f} EUR.
- At least {criteria.min_history_years:,.0f} years of price history.

Use web_search to verify these facts before proposing an asset. Prefer well
known, liquid, currently-listed instruments. Return only valid ticker symbols
with a one-line rationale each. If you cannot verify enough assets, return
fewer rather than guessing.
""".strip()


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
    ) -> str:
        return build_recommendation_prompt(categories, count, criteria, composition)

    def recommend(
        self,
        categories: list[str],
        count: int,
        criteria: EligibilityCriteria,
        composition: UniverseComposition,
    ) -> RecommendationResult:
        prompt = self.build_prompt(categories, count, criteria, composition)
        return asyncio.run(self._run(prompt))

    async def _run(self, prompt: str) -> RecommendationResult:
        agent = build_agent(
            name=_AGENT_NAME,
            instructions=_AGENT_INSTRUCTIONS,
            output_type=RecommendationOutput,
            tools=[web_search],
        )
        result = await asyncio.wait_for(
            Runner.run(agent, prompt, max_turns=AGENT_MAX_TURNS),
            timeout=AGENT_TIMEOUT_SECONDS,
        )
        output: RecommendationOutput = result.final_output
        tool_call_count = sum(
            1 for item in result.new_items if isinstance(item, ToolCallItem)
        )
        return RecommendationResult(output=output, tool_call_count=tool_call_count)
