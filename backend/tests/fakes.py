"""Test doubles for the market-data provider and recommender agent (no network)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

from cadence.ai_portfolio.agent import AIPortfolioBuildResult, AIRebalanceResult
from cadence.assets.market_data import AssetDetailData, AssetInfo, HistoryBar
from cadence.recommendations.agent import (
    EligibilityCriteria,
    RecommendationCandidate,
    RecommendationOutput,
    RecommendationResult,
    build_recommendation_prompt,
)
from cadence.recommendations.composition import UniverseComposition


class FakeMarketDataProvider:
    """In-memory :class:`MarketDataProvider` for tests.

    Any of ``info_error``/``history_error``/``fx_error``/``detail_error`` can be
    set to an exception instance to simulate provider failures. ``detail_calls``
    counts the number of ``fetch_detail`` invocations so tests can assert the
    once-per-day cache avoids the provider.
    """

    def __init__(
        self,
        *,
        info: AssetInfo | None = None,
        history: list[HistoryBar] | None = None,
        fx_rates: dict[str, float] | None = None,
        detail: AssetDetailData | None = None,
        info_error: Exception | None = None,
        history_error: Exception | None = None,
        fx_error: Exception | None = None,
        detail_error: Exception | None = None,
        history_by_ticker: dict[str, list[HistoryBar]] | None = None,
        history_error_by_ticker: dict[str, Exception] | None = None,
    ) -> None:
        self._info = info
        self._history = history or []
        self._fx_rates = fx_rates or {}
        self._detail = detail
        self._info_error = info_error
        self._history_error = history_error
        self._fx_error = fx_error
        self._detail_error = detail_error
        # Per-ticker overrides let a test vary history (or raise) by ticker.
        self._history_by_ticker = history_by_ticker or {}
        self._history_error_by_ticker = history_error_by_ticker or {}
        self.detail_calls = 0
        self.history_calls: list[str] = []

    def fetch_info(self, ticker: str) -> AssetInfo:
        if self._info_error is not None:
            raise self._info_error
        assert self._info is not None, "FakeMarketDataProvider has no info configured"
        return self._info

    def fetch_history(self, ticker: str) -> list[HistoryBar]:
        self.history_calls.append(ticker)
        if ticker in self._history_error_by_ticker:
            raise self._history_error_by_ticker[ticker]
        if self._history_error is not None:
            raise self._history_error
        if ticker in self._history_by_ticker:
            return self._history_by_ticker[ticker]
        return self._history

    def fetch_fx_rate(self, currency: str) -> float:
        if self._fx_error is not None:
            raise self._fx_error
        if currency.upper() == "EUR":
            return 1.0
        return self._fx_rates[currency.upper()]

    def fetch_detail(self, ticker: str) -> AssetDetailData:
        self.detail_calls += 1
        if self._detail_error is not None:
            raise self._detail_error
        assert (
            self._detail is not None
        ), "FakeMarketDataProvider has no detail configured"
        return self._detail


class FakeRecommenderAgent:
    """In-memory :class:`RecommenderAgent` returning canned candidates.

    Set ``error`` to raise from :meth:`recommend` (to drive failure paths).
    ``recommend_calls`` records the ``(categories, count)`` of each call. The
    prompt is built with the real builder so the recorded prompt is realistic.
    """

    def __init__(
        self,
        *,
        candidates: list[RecommendationCandidate] | None = None,
        tool_call_count: int = 0,
        error: Exception | None = None,
    ) -> None:
        self._candidates = candidates or []
        self._tool_call_count = tool_call_count
        self._error = error
        self.recommend_calls: list[tuple[list[str], int]] = []

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
        self.recommend_calls.append((list(categories), count))
        if self._error is not None:
            raise self._error
        return RecommendationResult(
            output=RecommendationOutput(candidates=list(self._candidates)),
            tool_call_count=self._tool_call_count,
        )


class FakeAIPortfolioAgent:
    """In-memory :class:`AIPortfolioAgent` returning canned structured output.

    Set ``build_error``/``rebalance_error`` to drive failure paths. ``build_calls``
    and ``rebalance_calls`` record the keyword arguments of each call so tests can
    assert the service passed flags (risk profile, allow_short, ...) through.
    """

    def __init__(
        self,
        *,
        build_result: AIPortfolioBuildResult | None = None,
        rebalance_result: AIRebalanceResult | None = None,
        build_error: Exception | None = None,
        rebalance_error: Exception | None = None,
    ) -> None:
        self._build_result = build_result
        self._rebalance_result = rebalance_result
        self._build_error = build_error
        self._rebalance_error = rebalance_error
        self.build_calls: list[dict[str, Any]] = []
        self.rebalance_calls: list[dict[str, Any]] = []

    def build(
        self,
        candidates: list[dict[str, Any]],
        risk_profile: str,
    ) -> AIPortfolioBuildResult:
        self.build_calls.append(
            {
                "candidates": candidates,
                "risk_profile": risk_profile,
            }
        )
        if self._build_error is not None:
            raise self._build_error
        assert self._build_result is not None, "FakeAIPortfolioAgent has no build_result"
        return self._build_result

    def rebalance(
        self,
        holdings: list[dict[str, Any]],
        account_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> AIRebalanceResult:
        self.rebalance_calls.append(
            {
                "holdings": holdings,
                "account_summary": account_summary,
                "candidates": candidates,
            }
        )
        if self._rebalance_error is not None:
            raise self._rebalance_error
        assert (
            self._rebalance_result is not None
        ), "FakeAIPortfolioAgent has no rebalance_result"
        return self._rebalance_result


class ManualExecutor:
    """An executor that captures submitted jobs and runs them on demand.

    Satisfies the job runner's executor seam. Jobs are NOT run on ``submit`` (so
    tests can assert the caller returns before completion); call
    :meth:`run_pending` to execute them synchronously in the calling thread.
    ``fail_workers=True`` makes :meth:`run_pending` swallow job exceptions and
    complete the future with them, simulating a dead worker.
    """

    def __init__(self, *, run_immediately: bool = False) -> None:
        self._run_immediately = run_immediately
        self._pending: list[tuple[Future, Callable[..., object], tuple[object, ...]]] = []

    def submit(self, fn: Callable[..., object], /, *args: object) -> Future:
        future: Future = Future()
        if self._run_immediately:
            self._execute(future, fn, args)
        else:
            self._pending.append((future, fn, args))
        return future

    def run_pending(self) -> None:
        pending, self._pending = self._pending, []
        for future, fn, args in pending:
            self._execute(future, fn, args)

    @staticmethod
    def _execute(
        future: Future,
        fn: Callable[..., object],
        args: tuple[object, ...],
    ) -> None:
        try:
            future.set_result(fn(*args))
        except Exception as exc:  # noqa: BLE001 - surfaced via the future
            future.set_exception(exc)
