"""The orchestrator's AI decision agent.

Given the run's briefing, the agent returns a structured :class:`OrchestratorDecision`:
a market summary, bots to stop, and preset bots to deploy. It may web-search market
and sector news within a per-run budget. It never acts itself — every action is
validated and applied deterministically by :mod:`.runs`.

The production implementation wraps ``openai-agents``; tests inject a fake through
the :class:`OrchestratorAgent` protocol. Timeouts and SDK failures surface as
:class:`OrchestratorUnavailableError` so the run fails with a readable message.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Any, Protocol, runtime_checkable

from agents.run import Runner
from pydantic import BaseModel, Field

from cadence.agents import build_agent, run_config_for_trace
from cadence.agents.tools import web_search, web_search_budget
from cadence.bot_orchestrator.errors import OrchestratorUnavailableError
from cadence.config import settings

#: Bumped whenever the instructions or prompt layout change; stored on each run.
ORCHESTRATOR_PROMPT_VERSION = 2

_AGENT_NAME = "BotOrchestratorAgent"

_AGENT_INSTRUCTIONS = """
You manage a small portfolio of deterministic, long-only US-equity trading bots on a
paper account. Each bot runs one fixed strategy preset from a course catalog on a few
tickers with its own capital, take-profit, stop-loss and drawdown kill-switch. You do
not trade yourself: once a day before the market opens you decide which running bots
to STOP and which preset bots to DEPLOY. Bots act from the opening bell.

Decide from the briefing (market technicals, sector breadth and news tone, candidate
tickers, strategies, presets, your running bots, and your limits). You may run a few web searches
for current market or sector news; use them only when they add something the briefing
lacks.

Guidelines:
- Prefer few, deliberate changes. Doing nothing is often right. Do not churn: avoid
  stopping a bot that has run only a day or two unless it is clearly broken or its
  setup is gone.
- Each preset names its strategy; the Strategies section explains how each one trades
  and gives its style. Match styles to conditions: trend, momentum and breakout presets
  suit names and sectors in an up-trend regime with healthy breadth; mean-reversion
  presets suit liquid names that have pulled back inside an intact longer-term trend;
  regime-switching presets suit names whose regime is unclear or changing.
- Diversify across presets and sectors rather than stacking similar bots.
- Choose tickers only from the candidate list, at most the per-bot ticker limit.
- Respect every limit: capital per bot between the minimum and the per-bot maximum, the
  total of new deploys within free capital, and active bots within the parallel-bot
  limit (a bot you stop frees its slot at once, but its cash returns only after its
  positions are sold — do not count on it).
- Use exact preset keys and bot ids from the briefing.

Return a short market summary (2-4 sentences), then the stops and deploys, each with a
concise reason or rationale. Return empty lists when nothing should change.
"""


class StopAction(BaseModel):
    """Stop one of the orchestrator's running bots."""

    bot_id: str = Field(description="The id of a running bot from the briefing.")
    reason: str = Field(description="Why this bot should stop now.")


class DeployAction(BaseModel):
    """Deploy one new bot from a catalog preset."""

    preset_key: str = Field(description="An exact preset key from the briefing.")
    tickers: list[str] = Field(description="Tickers from the candidate list.")
    capital: float = Field(description="Capital in USD for this bot.")
    rationale: str = Field(description="Why this preset fits these tickers now.")


class OrchestratorDecision(BaseModel):
    """The agent's structured decision for one run."""

    market_summary: str = Field(description="2-4 sentence read of the market.")
    stops: list[StopAction] = Field(default_factory=list)
    deploys: list[DeployAction] = Field(default_factory=list)


@dataclass(frozen=True)
class RunUsage:
    """Token usage of one decision run's AI call (all model requests it made)."""

    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int

    def as_dict(self) -> dict[str, int]:
        """JSON-ready form stored on the run."""
        return asdict(self)


@dataclass(frozen=True)
class OrchestratorAgentResult:
    """The agent's decision together with the token usage that produced it."""

    decision: OrchestratorDecision
    #: ``None`` when the SDK reported no usage.
    usage: RunUsage | None


def usage_from_sdk(usage: Any) -> RunUsage | None:
    """Map the SDK's run usage (``result.context_wrapper.usage``) to :class:`RunUsage`."""
    if usage is None:
        return None
    return RunUsage(
        requests=int(getattr(usage, "requests", 0) or 0),
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
    )


def _section(title: str, payload: Any) -> str:
    return f"## {title}\n{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"


def build_orchestrator_prompt(briefing: dict[str, Any]) -> str:
    """Render the briefing as deterministic prompt sections."""
    sectors = briefing.get("sectors", {})
    return "\n\n".join(
        [
            f"Briefing as of {briefing.get('as_of')}.",
            _section("Limits", briefing.get("limits")),
            _section("Market technicals (indices)", briefing.get("market")),
            _section("Sector breadth", sectors.get("breadth")),
            _section("Sector news tone", sectors.get("news_tone")),
            _section("Strategies", briefing.get("strategies")),
            _section("Presets", briefing.get("presets")),
            _section("Running bots", briefing.get("running_bots")),
            _section(
                "Stopped bots still being sold (no action needed)",
                briefing.get("liquidating_bots"),
            ),
            _section("Candidate tickers", briefing.get("candidates")),
        ]
    )


@runtime_checkable
class OrchestratorAgent(Protocol):
    """Produces a decision for a briefing. Raises ``OrchestratorUnavailableError``."""

    def decide(
        self, briefing: dict[str, Any], *, model: str
    ) -> OrchestratorAgentResult:
        """Return the structured decision for ``briefing`` and its token usage."""
        ...


class OpenAIOrchestratorAgent:
    """Production :class:`OrchestratorAgent` backed by ``openai-agents``."""

    def decide(
        self, briefing: dict[str, Any], *, model: str
    ) -> OrchestratorAgentResult:
        return asyncio.run(self._run(build_orchestrator_prompt(briefing), model))

    async def _run(self, prompt: str, model: str) -> OrchestratorAgentResult:
        agent = build_agent(
            name=_AGENT_NAME,
            instructions=_AGENT_INSTRUCTIONS,
            output_type=OrchestratorDecision,
            tools=[web_search],
            model=model,
        )
        timeout = settings.BOT_ORCHESTRATOR_TIMEOUT_SECONDS
        try:
            with web_search_budget(settings.BOT_ORCHESTRATOR_MAX_WEB_SEARCHES):
                result = await asyncio.wait_for(
                    Runner.run(
                        agent,
                        prompt,
                        max_turns=settings.BOT_ORCHESTRATOR_MAX_TURNS,
                        run_config=run_config_for_trace(),
                    ),
                    timeout=timeout,
                )
        except TimeoutError as exc:
            raise OrchestratorUnavailableError(
                f"The orchestrator decision timed out after {timeout}s."
            ) from exc
        except Exception as exc:
            raise OrchestratorUnavailableError(
                f"The orchestrator decision could not be produced: {exc}"
            ) from exc
        output: OrchestratorDecision = result.final_output
        return OrchestratorAgentResult(
            decision=output,
            usage=usage_from_sdk(getattr(result.context_wrapper, "usage", None)),
        )
