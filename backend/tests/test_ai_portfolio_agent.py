"""Tests for the AI portfolio agent: output-model contracts, prompt builders, the
sync-over-async entrypoints (with the SDK ``Runner`` patched out — no network), and
the hard per-run web-search budget."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from cadence.agents import tools as tools_module
from cadence.agents.tools import (
    BUDGET_EXHAUSTED_MESSAGE,
    _run_web_search,
    web_search_budget,
)
from cadence.ai_portfolio import agent as agent_module
from cadence.ai_portfolio.agent import (
    AIPortfolioBuildResult,
    AIPortfolioStock,
    AIRebalanceResult,
    AITargetAllocation,
    PositionSide,
    _build_portfolio_input,
    _build_rebalance_input,
    build_ai_portfolio,
    rebalance_ai_portfolio,
)
from cadence.config import settings


def _valid_build_result() -> AIPortfolioBuildResult:
    return AIPortfolioBuildResult(
        portfolio_name="Test Portfolio",
        stocks=[
            AIPortfolioStock(
                ticker="AAPL",
                company_name="Apple",
                side=PositionSide.LONG,
                allocation_pct=0.5,
                investment_thesis="Strong",
                confidence=0.8,
            ),
            AIPortfolioStock(
                ticker="MSFT",
                company_name="Microsoft",
                allocation_pct=0.5,
                investment_thesis="Cloud",
                confidence=0.9,
            ),
        ],
        overall_thesis="Diversified tech",
        risk_assessment="Concentration risk",
    )


# --------------------------------------------------------------------------- #
# Output model contracts
# --------------------------------------------------------------------------- #


def test_stock_allocation_bounds_enforced() -> None:
    # allocation_pct is now a fraction in [0, 1]; > 1.0 is rejected.
    with pytest.raises(ValueError):
        AIPortfolioStock(
            ticker="AAPL",
            company_name="Apple",
            allocation_pct=1.5,
            investment_thesis="x",
            confidence=0.5,
        )


def test_stock_allocation_allows_full_range() -> None:
    # No lower cap (0.0 excludes) and no upper cap below 1.0 any more.
    for alloc in (0.0, 0.03, 0.9, 1.0):
        stock = AIPortfolioStock(
            ticker="AAPL",
            company_name="Apple",
            allocation_pct=alloc,
            investment_thesis="x",
            confidence=0.5,
        )
        assert stock.allocation_pct == alloc
        assert stock.side == PositionSide.LONG


def test_build_result_allows_single_stock() -> None:
    # min_length/max_length were removed: a single-stock portfolio is valid.
    result = AIPortfolioBuildResult(
        portfolio_name="P",
        stocks=[
            AIPortfolioStock(
                ticker="AAPL",
                company_name="Apple",
                allocation_pct=1.0,
                investment_thesis="x",
                confidence=0.5,
            )
        ],
        overall_thesis="x",
        risk_assessment="x",
    )
    assert len(result.stocks) == 1


def test_rebalance_result_defaults_target_allocations_to_empty() -> None:
    result = AIRebalanceResult(
        evaluation_summary="ok",
        portfolio_health="healthy",
    )
    assert result.target_allocations == []


def test_target_allocation_bounds_enforced() -> None:
    with pytest.raises(ValueError):
        AITargetAllocation(
            ticker="AAPL",
            company_name="Apple",
            allocation_pct=1.5,
            investment_thesis="x",
            confidence=0.5,
        )


# --------------------------------------------------------------------------- #
# Prompt builders
# --------------------------------------------------------------------------- #


def test_build_portfolio_input_reflects_universe_and_risk() -> None:
    candidates = [{"ticker": "AAPL"}]
    prompt = _build_portfolio_input(candidates, "aggressive")
    assert "aggressive" in prompt
    assert "sum to approximately 1.0" in prompt
    assert "AAPL" in prompt


def _load_seed_migration() -> ModuleType:
    """Load the seed migration module by path to read its embedded seed text."""
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "a1d4e7c2b9f8_add_rebalance_prompt_table.py"
    )
    spec = importlib.util.spec_from_file_location("_rebalance_seed_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_fills_placeholders_and_is_brace_safe() -> None:
    # Only known tokens are replaced; stray braces in a value pass through intact.
    rendered = agent_module._render(
        "risk={risk} data={blob}",
        risk="aggressive",
        blob='{"a": 1, "nested": {"b": 2}}',
    )
    assert rendered == 'risk=aggressive data={"a": 1, "nested": {"b": 2}}'


def test_build_rebalance_input_renders_template_sections() -> None:
    template = _load_seed_migration()._SEED_INPUT_TEMPLATE
    prompt = _build_rebalance_input(
        template,
        holdings=[{"ticker": "AAPL"}],
        account_summary={"cash_available": 1000},
        candidates=[{"ticker": "MSFT"}],
        risk_profile="aggressive",
    )
    assert "Current Holdings" in prompt
    assert "Account Summary" in prompt
    assert "long only" in prompt
    assert "target weights" in prompt
    # The run values are substituted, and no placeholder tokens remain.
    assert "aggressive" in prompt
    assert '"ticker": "AAPL"' in prompt
    assert '"ticker": "MSFT"' in prompt
    assert "{" + "risk_profile" + "}" not in prompt
    assert "{holdings_json}" not in prompt


def test_seeded_rebalance_prompt_matches_legacy_output() -> None:
    """The migration-seeded v1 renders byte-for-byte to the old hardcoded prompt."""
    seed = _load_seed_migration()

    instructions = agent_module._render(
        seed._SEED_INSTRUCTIONS,
        max_new_assets=str(settings.AI_PORTFOLIO_MAX_NEW_ASSETS),
        max_web_searches=str(settings.AI_PORTFOLIO_MAX_WEB_SEARCHES),
    )
    expected_instructions = f"""
You are a portfolio manager reviewing an existing LONG-ONLY buy-and-hold portfolio.
Given the current holdings, account summary, and the full candidate universe, decide the
desired END-STATE target weights for the portfolio and return them as target_allocations.

Requirements:
- All positions are LONG; never propose short positions
- Return desired end-state target weights (allocation_pct in 0.0-1.0) per ticker
- allocation_pct values across all target_allocations must sum to approximately 1.0
- Any asset that should be EXITED must be omitted (or given a ~0 target weight)
- Be conservative: buy-and-hold means holding through normal volatility, so only
  change weights materially when there are real, evidence-based reasons
- Use the web_search tool to check latest news and fundamentals
- Candidates may include crypto assets (shown via their ``category``); crypto uses
  yfinance-style tickers like ``BTC-USD`` and trades 24/7. Weight any crypto
  according to the portfolio's risk profile.

Discovery and cost controls:
- You may include assets NOT in the current holdings or universe if compelling.
- You may discover at most {settings.AI_PORTFOLIO_MAX_NEW_ASSETS} assets beyond the universe.
- Perform at most {settings.AI_PORTFOLIO_MAX_WEB_SEARCHES} web searches total across this task; batch your research.
"""
    assert instructions == expected_instructions

    holdings = [{"ticker": "AAPL"}]
    account = {"cash_available": 5000}
    candidates = [{"ticker": "MSFT"}]
    rebalance_input = _build_rebalance_input(
        seed._SEED_INPUT_TEMPLATE,
        holdings=holdings,
        account_summary=account,
        candidates=candidates,
        risk_profile="balanced",
    )
    holdings_json = json.dumps(holdings, indent=2)
    account_json = json.dumps(account, indent=2)
    candidates_json = json.dumps(candidates, indent=2)
    expected_input = f"""
Review this portfolio and return the desired end-state target weights (target_allocations)
for a balanced long-only buy-and-hold portfolio.
All positions are long only. Weights across all targets must sum to approximately 1.0.
Omit (or set to ~0) any asset that should be exited.

Current Holdings:
{holdings_json}

Account Summary:
{account_json}

Candidate universe (JSON):
{candidates_json}
"""
    assert rebalance_input == expected_input


# --------------------------------------------------------------------------- #
# Sync-over-async entrypoints (Runner patched)
# --------------------------------------------------------------------------- #


class _FakeResult:
    def __init__(self, final_output: Any) -> None:
        self.final_output = final_output


def _patch_runner(monkeypatch: pytest.MonkeyPatch, output: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _FakeRunner:
        @staticmethod
        async def run(agent: Any, prompt: str, max_turns: int) -> _FakeResult:
            captured["prompt"] = prompt
            captured["max_turns"] = max_turns
            return _FakeResult(output)

    monkeypatch.setattr(agent_module, "Runner", _FakeRunner)
    return captured


def test_build_ai_portfolio_returns_final_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _valid_build_result()
    captured = _patch_runner(monkeypatch, expected)

    result = build_ai_portfolio(
        candidates=[{"ticker": "AAPL"}, {"ticker": "MSFT"}],
        risk_profile="balanced",
    )

    assert result is expected
    assert captured["max_turns"] == settings.AI_PORTFOLIO_MAX_TURNS
    assert "balanced" in captured["prompt"]


def test_rebalance_ai_portfolio_returns_final_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = AIRebalanceResult(
        evaluation_summary="ok",
        target_allocations=[
            AITargetAllocation(
                ticker="NVDA",
                company_name="Nvidia",
                allocation_pct=0.2,
                investment_thesis="AI",
                confidence=0.9,
            )
        ],
        portfolio_health="healthy",
    )
    captured = _patch_runner(monkeypatch, expected)

    result = rebalance_ai_portfolio(
        holdings=[{"ticker": "AAPL"}],
        account_summary={"cash_available": 5000},
        candidates=[{"ticker": "NVDA"}],
        risk_profile="balanced",
        instructions="caps {max_new_assets}/{max_web_searches}",
        input_template="rebalance {risk_profile}: {candidates_json}",
    )

    assert result is expected
    assert captured["max_turns"] == settings.AI_PORTFOLIO_MAX_TURNS
    # The versioned input template is rendered and handed to the Runner.
    assert captured["prompt"] == 'rebalance balanced: [\n  {\n    "ticker": "NVDA"\n  }\n]'


# --------------------------------------------------------------------------- #
# Web-search budget (hard cost cap; SerpAPI monkeypatched — no network)
# --------------------------------------------------------------------------- #


class _FakeSerpResults:
    @staticmethod
    def as_dict() -> dict[str, Any]:
        return {"organic_results": []}


class _CountingSerpClient:
    """Records how many SerpAPI searches were actually issued."""

    calls = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def search(self, params: dict[str, Any]) -> _FakeSerpResults:
        type(self).calls += 1
        return _FakeSerpResults()


def test_web_search_budget_stops_calling_serpapi_once_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CountingSerpClient.calls = 0
    monkeypatch.setattr(settings, "SERP_API_KEY", "test-key")
    monkeypatch.setattr(tools_module.serpapi, "Client", _CountingSerpClient)

    async def _drive() -> list[dict[str, Any]]:
        with web_search_budget(2):
            return [
                await _run_web_search("q1"),
                await _run_web_search("q2"),
                await _run_web_search("q3"),  # over budget
            ]

    results = asyncio.run(_drive())

    # First two searches hit the (fake) client; the third is refused with no call.
    assert _CountingSerpClient.calls == 2
    assert results[2] == {"error": BUDGET_EXHAUSTED_MESSAGE}
    assert "error" not in results[0]


def test_web_search_without_budget_is_unbounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CountingSerpClient.calls = 0
    monkeypatch.setattr(settings, "SERP_API_KEY", "test-key")
    monkeypatch.setattr(tools_module.serpapi, "Client", _CountingSerpClient)

    async def _drive() -> None:
        for _ in range(5):
            await _run_web_search("q")

    asyncio.run(_drive())
    assert _CountingSerpClient.calls == 5
