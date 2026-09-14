"""Tests for the AI portfolio agent: output-model contracts, prompt builders, and
the sync-over-async entrypoints (with the SDK ``Runner`` patched out — no network)."""

from __future__ import annotations

from typing import Any

import pytest

from cadence.ai_portfolio import agent as agent_module
from cadence.ai_portfolio.agent import (
    AIPortfolioBuildResult,
    AIPortfolioStock,
    AIRebalanceResult,
    ExistingHoldingEvaluation,
    NewStockRecommendation,
    PositionSide,
    RebalanceAction,
    _build_portfolio_input,
    _build_rebalance_input,
    build_ai_portfolio,
    rebalance_ai_portfolio,
)


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
                side=PositionSide.LONG,
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
    with pytest.raises(ValueError):
        AIPortfolioStock(
            ticker="AAPL",
            company_name="Apple",
            side=PositionSide.LONG,
            allocation_pct=0.9,  # > 0.5 max
            investment_thesis="x",
            confidence=0.5,
        )


def test_build_result_requires_at_least_two_stocks() -> None:
    with pytest.raises(ValueError):
        AIPortfolioBuildResult(
            portfolio_name="P",
            stocks=[
                AIPortfolioStock(
                    ticker="AAPL",
                    company_name="Apple",
                    side=PositionSide.LONG,
                    allocation_pct=0.5,
                    investment_thesis="x",
                    confidence=0.5,
                )
            ],
            overall_thesis="x",
            risk_assessment="x",
        )


def test_rebalance_result_defaults_new_recommendations_to_empty() -> None:
    result = AIRebalanceResult(
        evaluation_summary="ok",
        existing_holdings=[
            ExistingHoldingEvaluation(
                ticker="AAPL", action=RebalanceAction.HOLD, reasoning="x", confidence=0.6
            )
        ],
        portfolio_health="healthy",
    )
    assert result.new_recommendations == []


# --------------------------------------------------------------------------- #
# Prompt builders
# --------------------------------------------------------------------------- #


def test_build_portfolio_input_reflects_flags() -> None:
    candidates = [{"ticker": "AAPL"}]
    prompt = _build_portfolio_input(
        candidates, "aggressive", allow_new_picks=True, allow_short=True, max_stock_count=5
    )
    assert "aggressive" in prompt
    assert "up to 5 stocks" in prompt
    assert "discover stocks beyond this list" in prompt
    assert "include short positions" in prompt
    assert "AAPL" in prompt


def test_build_portfolio_input_long_only_and_candidates_only() -> None:
    prompt = _build_portfolio_input(
        [{"ticker": "X"}], "balanced", allow_new_picks=False, allow_short=False
    )
    assert "Select ONLY from the candidates" in prompt
    assert "All positions must be long" in prompt


def test_build_rebalance_input_includes_sections() -> None:
    prompt = _build_rebalance_input(
        holdings=[{"ticker": "AAPL"}],
        account_summary={"cash_available": 1000},
        candidates=[{"ticker": "MSFT"}],
        allow_short=False,
    )
    assert "Current Holdings" in prompt
    assert "Account Summary" in prompt
    assert "must be long only" in prompt


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
    assert captured["max_turns"] == agent_module.AGENT_MAX_TURNS
    assert "balanced" in captured["prompt"]


def test_rebalance_ai_portfolio_returns_final_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = AIRebalanceResult(
        evaluation_summary="ok",
        existing_holdings=[],
        new_recommendations=[
            NewStockRecommendation(
                ticker="NVDA",
                company_name="Nvidia",
                side=PositionSide.LONG,
                allocation_pct=0.2,
                investment_thesis="AI",
                confidence=0.9,
            )
        ],
        portfolio_health="healthy",
    )
    _patch_runner(monkeypatch, expected)

    result = rebalance_ai_portfolio(
        holdings=[{"ticker": "AAPL"}],
        account_summary={"cash_available": 5000},
        candidates=[{"ticker": "NVDA"}],
    )

    assert result is expected
