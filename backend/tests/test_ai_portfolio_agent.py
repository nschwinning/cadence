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
    GuardrailInstruction,
    PositionSide,
    _build_portfolio_input,
    _build_rebalance_input,
    _summarize_recent_outcomes,
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


def test_build_portfolio_input_includes_guardrails_when_enabled() -> None:
    guardrails = GuardrailInstruction(
        max_per_asset=0.25,
        max_per_class=0.6,
        min_positions=5,
        max_invested=0.9,
    )
    prompt = _build_portfolio_input([{"ticker": "AAPL"}], "balanced", guardrails)
    assert "Risk guardrails" in prompt
    assert "25%" in prompt  # max per asset
    assert "60%" in prompt  # max per class
    assert "5" in prompt  # min positions
    assert "90%" in prompt  # max invested


def test_build_portfolio_input_omits_guardrails_when_absent() -> None:
    prompt = _build_portfolio_input([{"ticker": "AAPL"}], "balanced")
    assert "Risk guardrails" not in prompt


def _load_migration(filename: str) -> ModuleType:
    """Load a migration module by filename to read its embedded seed text."""
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.rsplit(".", 1)[0], path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_seed_migration() -> ModuleType:
    """Load the v1 seed migration module (embeds the original hardcoded prompt)."""
    return _load_migration("a1d4e7c2b9f8_add_rebalance_prompt_table.py")


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


def test_build_rebalance_input_includes_guardrails_when_enabled() -> None:
    template = _load_seed_migration()._SEED_INPUT_TEMPLATE
    guardrails = GuardrailInstruction(
        max_per_asset=0.2,
        max_per_class=0.5,
        min_positions=4,
        max_invested=0.95,
    )
    prompt = _build_rebalance_input(
        template,
        holdings=[{"ticker": "AAPL"}],
        account_summary={"cash_available": 1000},
        candidates=[{"ticker": "MSFT"}],
        risk_profile="balanced",
        guardrails=guardrails,
    )
    assert "Risk guardrails" in prompt
    assert "20%" in prompt
    assert "50%" in prompt
    assert "95%" in prompt


def test_build_rebalance_input_omits_guardrails_when_absent() -> None:
    template = _load_seed_migration()._SEED_INPUT_TEMPLATE
    prompt = _build_rebalance_input(
        template,
        holdings=[{"ticker": "AAPL"}],
        account_summary={"cash_available": 1000},
        candidates=[{"ticker": "MSFT"}],
        risk_profile="balanced",
    )
    assert "Risk guardrails" not in prompt


def _outcome(
    run_date: str,
    *,
    realized_pnl: float | None = None,
    fees_total: float | None = None,
    orders_count: int | None = None,
    total_value: float | None = None,
    daily_pnl_pct: float | None = None,
    dropped: int | None = None,
) -> dict[str, Any]:
    run_stats: dict[str, Any] = {}
    if realized_pnl is not None:
        run_stats["realized_pnl"] = realized_pnl
    if dropped is not None:
        run_stats["gate"] = {"dropped": dropped}
    valuation: dict[str, Any] = {}
    if total_value is not None:
        valuation["total_value"] = total_value
    if daily_pnl_pct is not None:
        valuation["daily_pnl_pct"] = daily_pnl_pct
    document: dict[str, Any] = {"run": {"run_stats": run_stats}, "valuation": valuation}
    if fees_total is not None:
        document["fees_total"] = fees_total
    if orders_count is not None:
        document["orders_count"] = orders_count
    return {"run_date": run_date, "document": document}


def test_summarize_recent_outcomes_is_cost_forward() -> None:
    summary = _summarize_recent_outcomes(
        [
            _outcome(
                "2026-01-05",
                realized_pnl=50.0,
                fees_total=12.5,
                orders_count=3,
                total_value=101_000.0,
                daily_pnl_pct=0.0125,
                dropped=2,
            )
        ]
    )
    assert summary is not None
    # Net realized P&L = gross 50 − fees 12.5 = 37.5, and fees are called out explicitly.
    assert "net realized P&L +$37.50" in summary
    assert "fees $12.50" in summary
    assert "3 orders" in summary
    assert "end value $101,000.00 (+1.25%)" in summary
    assert "2 candidates gated out" in summary
    assert summary.startswith("- 2026-01-05:")


def test_summarize_recent_outcomes_tolerates_missing_fields() -> None:
    # A document with no run stats / valuation still yields a line (fees default to $0).
    summary = _summarize_recent_outcomes([{"run_date": "2026-01-04", "document": {}}])
    assert summary == "- 2026-01-04: fees $0.00"
    # Entirely empty / malformed input yields no section.
    assert _summarize_recent_outcomes([]) is None
    assert _summarize_recent_outcomes([{"run_date": "x", "document": None}]) is None


def test_build_rebalance_input_includes_recent_outcomes_when_given() -> None:
    template = _load_seed_migration()._SEED_INPUT_TEMPLATE
    prompt = _build_rebalance_input(
        template,
        holdings=[{"ticker": "AAPL"}],
        account_summary={"cash_available": 1000},
        candidates=[{"ticker": "MSFT"}],
        risk_profile="balanced",
        recent_outcomes=[
            _outcome("2026-01-05", realized_pnl=50.0, fees_total=12.5, orders_count=3)
        ],
    )
    assert "Recent run outcomes" in prompt
    assert "net realized P&L +$37.50" in prompt


def test_build_rebalance_input_omits_recent_outcomes_when_none_or_empty() -> None:
    template = _load_seed_migration()._SEED_INPUT_TEMPLATE
    base_kwargs: dict[str, Any] = {
        "holdings": [{"ticker": "AAPL"}],
        "account_summary": {"cash_available": 1000},
        "candidates": [{"ticker": "MSFT"}],
        "risk_profile": "balanced",
    }
    assert "Recent run outcomes" not in _build_rebalance_input(template, **base_kwargs)
    # An empty window (feature off / no snapshots) adds no section.
    assert "Recent run outcomes" not in _build_rebalance_input(
        template, recent_outcomes=[], **base_kwargs
    )


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


# The company-fundamentals block the v4 seed inserts verbatim before "Requirements:"
# (pinned here so a wording change to the seed must update this test deliberately).
_V4_FUNDAMENTALS_BLOCK = """Company fundamentals (optional context):
- When present, each candidate and holding ALSO carries a ``fundamentals`` object
  with the company's latest-annual financials. It has a ``status`` field; when
  ``status`` is ``available`` it may include ``gross_margin``, ``operating_margin``,
  and ``net_margin`` (profitability ratios, e.g. 0.42 = 42%), ``eps`` (diluted
  earnings per share, falling back to basic), and the absolute ``revenue``,
  ``net_income``, and ``operating_cash_flow`` (scale signals).
- This object is OPTIONAL. It is ABSENT entirely for sessions that did not opt into
  fundamentals, and marked ``{"status": "unavailable"}`` for any asset without
  usable data (for example a crypto asset or a company whose filings could not be
  read). Tolerate both cases: never assume a figure that is not shown.
- When a ``fundamentals`` object is present and available, weigh it alongside the
  technical picture: favour durable profitability and healthy cash generation, and
  be more cautious with deteriorating or loss-making fundamentals. Do NOT penalise
  an asset merely for lacking fundamentals, and never let fundamentals override a
  clear trend breakdown on a holding."""


def test_v4_seed_is_v3_verbatim_plus_fundamentals_block() -> None:
    """The v4 seed is the v3 prompt with only the fundamentals block added."""
    v3 = _load_migration("a7b8c9d0e1f2_seed_rebalance_prompt_v3.py")
    v4 = _load_migration("e8f3a1c5d2b4_seed_rebalance_prompt_v4.py")

    # The input template is the v3 template, byte-for-byte.
    assert v4._V4_INPUT_TEMPLATE == v3._V3_INPUT_TEMPLATE

    # The instructions are v3 verbatim with the fundamentals block inserted before
    # the Requirements section — nothing else changes.
    expected_instructions = v3._V3_INSTRUCTIONS.replace(
        "\n\nRequirements:\n",
        "\n\n" + _V4_FUNDAMENTALS_BLOCK + "\n\nRequirements:\n",
        1,
    )
    assert v4._V4_INSTRUCTIONS == expected_instructions


def test_v4_seed_renders_brace_safe() -> None:
    """``_render`` fills the cost placeholders and leaves the literal unavailable
    marker's braces untouched (brace-safety regression guard)."""
    v4 = _load_migration("e8f3a1c5d2b4_seed_rebalance_prompt_v4.py")
    rendered = agent_module._render(
        v4._V4_INSTRUCTIONS,
        max_new_assets=str(settings.AI_PORTFOLIO_MAX_NEW_ASSETS),
        max_web_searches=str(settings.AI_PORTFOLIO_MAX_WEB_SEARCHES),
    )
    assert '{"status": "unavailable"}' in rendered
    assert "{max_new_assets}" not in rendered
    assert "{max_web_searches}" not in rendered
    assert f"at most {settings.AI_PORTFOLIO_MAX_NEW_ASSETS} assets" in rendered


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
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "serpapi")
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
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "serpapi")
    monkeypatch.setattr(settings, "SERP_API_KEY", "test-key")
    monkeypatch.setattr(tools_module.serpapi, "Client", _CountingSerpClient)

    async def _drive() -> None:
        for _ in range(5):
            await _run_web_search("q")

    asyncio.run(_drive())
    assert _CountingSerpClient.calls == 5


# --------------------------------------------------------------------------- #
# Web-search provider dispatch (Serper + unknown; httpx monkeypatched — no network)
# --------------------------------------------------------------------------- #


class _FakeSerperResponse:
    """Minimal stand-in for an ``httpx.Response`` from serper.dev."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload


def test_serper_provider_is_used_and_normalises_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "serper")
    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")

    captured: dict[str, Any] = {}

    def _fake_post(url: str, **kwargs: Any) -> _FakeSerperResponse:
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return _FakeSerperResponse(
            {
                "organic": [
                    {
                        "title": "Serper result",
                        "link": "https://example.com/s",
                        "snippet": "A snippet",
                        "position": 1,
                    }
                ],
                "answerBox": {"answer": "42"},
            }
        )

    monkeypatch.setattr(tools_module.httpx, "post", _fake_post)

    result = asyncio.run(_run_web_search("what is x"))

    assert captured["url"] == tools_module.SERPER_SEARCH_URL
    assert captured["headers"] == {"X-API-KEY": "serper-key"}
    assert captured["json"]["q"] == "what is x"
    assert result["organic_results"] == [
        {
            "title": "Serper result",
            "link": "https://example.com/s",
            "snippet": "A snippet",
        }
    ]
    assert result["answer_box"] == {"answer": "42"}


def test_serper_missing_key_raises_provider_named_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "serper")
    monkeypatch.setattr(settings, "SERPER_API_KEY", "")

    with pytest.raises(ValueError, match="SERPER_API_KEY is not set"):
        asyncio.run(_run_web_search("q"))


def test_serper_non_200_surfaces_error_not_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "serper")
    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")

    def _fake_post(url: str, **kwargs: Any) -> _FakeSerperResponse:
        return _FakeSerperResponse({}, status_code=401)

    monkeypatch.setattr(tools_module.httpx, "post", _fake_post)

    result = asyncio.run(_run_web_search("q"))
    assert "error" in result
    assert "401" in result["error"]


def test_unrecognised_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "bing")

    with pytest.raises(ValueError, match="unrecognised value"):
        asyncio.run(_run_web_search("q"))


def test_serper_budget_short_circuits_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "serper")
    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")

    calls = {"n": 0}

    def _fake_post(url: str, **kwargs: Any) -> _FakeSerperResponse:
        calls["n"] += 1
        return _FakeSerperResponse({"organic": []})

    monkeypatch.setattr(tools_module.httpx, "post", _fake_post)

    async def _drive() -> list[dict[str, Any]]:
        with web_search_budget(1):
            return [
                await _run_web_search("q1"),
                await _run_web_search("q2"),  # over budget
            ]

    results = asyncio.run(_drive())

    assert calls["n"] == 1  # second search never reached Serper
    assert results[1] == {"error": BUDGET_EXHAUSTED_MESSAGE}
