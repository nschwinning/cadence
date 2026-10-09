"""The asset-universe evaluation agent and its structured contract.

The agent is asked to assess the whole asset universe — diversification,
sector/category concentration, quality, notable gaps, and foreign/unpriceable
listings — from a compact summary (not the raw rows), returning a Pydantic
:class:`UniverseEvaluationOutput`. :class:`UniverseEvaluationAgent` is the seam
service code depends on so tests can swap in a fake with no network. Unlike the
recommender, this agent uses no tools: it judges the supplied summary only.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from agents.run import Runner
from pydantic import BaseModel, Field

from cadence.agents import build_agent
from cadence.assets.errors import AssetEvaluationUnavailableError
from cadence.config import settings

_AGENT_NAME = "AssetUniverseEvaluationAgent"

_AGENT_INSTRUCTIONS = """
You are a portfolio construction analyst reviewing a curated universe of
tradable assets. Assess the universe as a whole — its diversification,
sector/category concentration, overall quality, notable gaps, and any foreign or
unpriceable listings that cannot be traded. Judge only the summary you are given;
do not invent assets or facts not present in it. Write a concise markdown
narrative plus short bulleted findings. Do not assign numeric scores or ratings.
Keep each bullet to a single, specific sentence.
""".strip()


@dataclass(frozen=True)
class UniverseSummary:
    """A compact, prompt-ready summary of the asset universe.

    Built by the service from the stored assets so the agent reasons about
    structure, not per-row data. ``category_counts`` and ``sector_counts`` map a
    label (a sector slug, or ``"none"`` for assets with no sector) to its count;
    ``top_concentrations`` lists the largest sector groups (label, count) for the
    concentration read; ``unpriceable_listings`` are tickers with no brokerage
    symbol (foreign/unpriceable listings).
    """

    total: int
    eligible_count: int
    ineligible_count: int
    category_counts: dict[str, int]
    sector_counts: dict[str, int]
    top_concentrations: list[tuple[str, int]]
    unpriceable_listings: list[str]


class UniverseEvaluationOutput(BaseModel):
    """The agent's structured evaluation of the universe."""

    narrative: str = Field(
        description="Markdown prose assessing the universe as a whole"
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Bulleted strengths of the current universe",
    )
    concerns: list[str] = Field(
        default_factory=list,
        description="Bulleted concerns or risks in the current universe",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Bulleted suggestions to improve the universe",
    )


@runtime_checkable
class UniverseEvaluationAgent(Protocol):
    """Seam for producing an AI evaluation of the asset universe.

    Implemented by :class:`OpenAIUniverseEvaluationAgent` in production and by a
    fake in tests. ``evaluate`` is synchronous so the service stays fully sync;
    the real implementation drives the async SDK internally.
    """

    def evaluate(self, summary: UniverseSummary) -> UniverseEvaluationOutput:
        """Return a structured evaluation of the given universe summary."""
        ...

    def build_prompt(self, summary: UniverseSummary) -> str:
        """Return the exact prompt text that would be sent for this summary."""
        ...


def _render_counts(counts: dict[str, int]) -> str:
    """Render a label→count map as ``label n, label n`` (largest first)."""
    if not counts:
        return "none"
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{label} {count}" for label, count in ordered)


def build_universe_evaluation_prompt(summary: UniverseSummary) -> str:
    """Compose the agent input from a universe summary.

    States the totals, eligibility split, category/sector composition, the
    largest concentrations, and any foreign/unpriceable listings, then asks for a
    narrative plus bulleted strengths/concerns/suggestions. Pure and
    deterministic for a given summary so it is unit-testable.
    """
    if summary.top_concentrations:
        concentration_line = ", ".join(
            f"{label} {count}" for label, count in summary.top_concentrations
        )
    else:
        concentration_line = "none"
    if summary.unpriceable_listings:
        unpriceable_line = (
            f"{len(summary.unpriceable_listings)} listing(s) with no tradable "
            f"brokerage symbol: {', '.join(summary.unpriceable_listings)}"
        )
    else:
        unpriceable_line = "none"
    return f"""
Assess this asset universe as a whole.

Totals: {summary.total} assets ({summary.eligible_count} eligible,
{summary.ineligible_count} ineligible).

By category: {_render_counts(summary.category_counts)}
By sector: {_render_counts(summary.sector_counts)}
Largest concentrations (sector): {concentration_line}
Foreign/unpriceable listings: {unpriceable_line}

Evaluate diversification, sector and category concentration, overall quality,
notable gaps, and the risk from any foreign or unpriceable listings. Respond with
a markdown narrative plus bulleted strengths, concerns, and suggestions. Do not
use numeric scores.
""".strip()


class OpenAIUniverseEvaluationAgent:
    """Production :class:`UniverseEvaluationAgent` backed by ``openai-agents``.

    Builds a tool-less structured-output agent and runs it once under a timeout.
    Reuses ``settings.RECOMMENDER_MODEL`` (no dedicated config key yet). A
    timeout or SDK failure is surfaced as :class:`AssetEvaluationUnavailableError`
    so the caller leaves any existing evaluation intact.
    """

    def build_prompt(self, summary: UniverseSummary) -> str:
        return build_universe_evaluation_prompt(summary)

    def evaluate(self, summary: UniverseSummary) -> UniverseEvaluationOutput:
        prompt = self.build_prompt(summary)
        return asyncio.run(self._run(prompt))

    async def _run(self, prompt: str) -> UniverseEvaluationOutput:
        agent = build_agent(
            name=_AGENT_NAME,
            instructions=_AGENT_INSTRUCTIONS,
            output_type=UniverseEvaluationOutput,
        )
        timeout = settings.RECOMMENDER_AGENT_TIMEOUT_SECONDS
        try:
            result = await asyncio.wait_for(
                Runner.run(agent, prompt, max_turns=1),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise AssetEvaluationUnavailableError(
                f"The universe evaluation timed out after {timeout}s."
            ) from exc
        except Exception as exc:
            raise AssetEvaluationUnavailableError(
                f"The universe evaluation could not be generated: {exc}"
            ) from exc
        output: UniverseEvaluationOutput = result.final_output
        return output


def get_universe_evaluation_model() -> str | None:
    """Return the model id used for evaluations (for persisting on the row)."""
    return settings.RECOMMENDER_MODEL
