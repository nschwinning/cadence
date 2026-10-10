"""Test doubles for the market-data provider and recommender agent (no network)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from datetime import date, timedelta
from typing import Any

from cadence.agents.tools import note_web_search
from cadence.ai_portfolio.agent import AIPortfolioBuildResult, AIRebalanceResult
from cadence.assets.market_data import AssetDetailData, AssetInfo, HistoryBar
from cadence.assets.universe_agent import (
    UniverseEvaluationOutput,
    UniverseSummary,
    build_universe_evaluation_prompt,
)
from cadence.broker.models import AssetClass, BrokerAsset
from cadence.broker.stub import StubBroker
from cadence.recommendations.agent import (
    EligibilityCriteria,
    RecommendationCandidate,
    RecommendationOutput,
    RecommendationResult,
    build_recommendation_prompt,
)
from cadence.recommendations.composition import UniverseComposition


def _synthetic_series(
    ticker: str, start: date, end: date
) -> list[tuple[date, float]]:
    """Deterministic per-ticker daily close series over ``[start, end]``.

    Stable across calls (no randomness): the base level is derived from the
    ticker and each day drifts by a fixed small step, so offline/stub mode
    yields a reproducible series per ticker.
    """

    base = 50.0 + float(sum(ord(ch) for ch in ticker) % 50)
    out: list[tuple[date, float]] = []
    day = start
    step = 0
    while day <= end:
        out.append((day, round(base * (1.0 + 0.0005 * step), 4)))
        day += timedelta(days=1)
        step += 1
    return out


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
        info_error_by_ticker: dict[str, Exception] | None = None,
        daily_closes_by_ticker: dict[str, list[tuple[date, float]]] | None = None,
        daily_closes_error: Exception | None = None,
        synthetic_closes: bool = False,
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
        # Per-ticker info errors drive the dotted->dash class-share fallback:
        # raise for ``BRK.B`` but succeed for ``BRK-B``.
        self._info_error_by_ticker = info_error_by_ticker or {}
        # Price-history batch closes: explicit per-ticker series win; otherwise a
        # synthetic deterministic series (when enabled) or the closes derived
        # from configured history bars are returned, so backfill/ingestion paths
        # work offline. A ticker with no source is simply absent from the result.
        self._daily_closes_by_ticker = daily_closes_by_ticker or {}
        self._daily_closes_error = daily_closes_error
        self._synthetic_closes = synthetic_closes
        self.detail_calls = 0
        self.history_calls: list[str] = []
        self.daily_closes_calls: list[list[str]] = []

    def fetch_info(self, ticker: str) -> AssetInfo:
        if ticker in self._info_error_by_ticker:
            raise self._info_error_by_ticker[ticker]
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
        if currency.upper() == "USD":
            return 1.0
        return self._fx_rates[currency.upper()]

    def fetch_daily_closes(
        self, tickers: list[str], start: date, end: date
    ) -> dict[str, list[tuple[date, float]]]:
        self.daily_closes_calls.append(list(tickers))
        if self._daily_closes_error is not None:
            raise self._daily_closes_error
        result: dict[str, list[tuple[date, float]]] = {}
        for ticker in tickers:
            series = self._daily_closes_for(ticker, start, end)
            if series:
                result[ticker] = sorted(series)
        return result

    def _daily_closes_for(
        self, ticker: str, start: date, end: date
    ) -> list[tuple[date, float]]:
        if ticker in self._daily_closes_by_ticker:
            return [
                (day, close)
                for day, close in self._daily_closes_by_ticker[ticker]
                if start <= day <= end
            ]
        if self._synthetic_closes:
            return _synthetic_series(ticker, start, end)
        bars = self._history_by_ticker.get(ticker, self._history)
        return [(bar.date, bar.close) for bar in bars if start <= bar.date <= end]

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
    ``recommend_calls`` records the ``(categories, count)`` of each call and
    ``exclude_calls`` records the exclusion list passed to each call. The prompt
    is built with the real builder so the recorded prompt is realistic.
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
        self.exclude_calls: list[list[str]] = []

    def build_prompt(
        self,
        categories: list[str],
        count: int,
        criteria: EligibilityCriteria,
        composition: UniverseComposition,
        exclude_tickers: list[str],
    ) -> str:
        return build_recommendation_prompt(
            categories, count, criteria, composition, exclude_tickers
        )

    def recommend(
        self,
        categories: list[str],
        count: int,
        criteria: EligibilityCriteria,
        composition: UniverseComposition,
        exclude_tickers: list[str],
    ) -> RecommendationResult:
        self.recommend_calls.append((list(categories), count))
        self.exclude_calls.append(list(exclude_tickers))
        if self._error is not None:
            raise self._error
        return RecommendationResult(
            output=RecommendationOutput(candidates=list(self._candidates)),
            tool_call_count=self._tool_call_count,
        )


class FakeUniverseEvaluationAgent:
    """In-memory :class:`UniverseEvaluationAgent` returning a canned evaluation.

    Set ``error`` to raise from :meth:`evaluate` (to drive the failure path that
    surfaces as HTTP 502 and leaves any existing evaluation intact).
    ``evaluate_calls`` records each :class:`UniverseSummary` passed so tests can
    assert the summary the service built. The prompt is built with the real
    builder so the recorded prompt is realistic.
    """

    def __init__(
        self,
        *,
        output: UniverseEvaluationOutput | None = None,
        error: Exception | None = None,
    ) -> None:
        self._output = output or UniverseEvaluationOutput(
            narrative="A reasonably diversified universe.",
            strengths=["Broad sector coverage"],
            concerns=["Some concentration in technology"],
            suggestions=["Add exposure to utilities"],
        )
        self._error = error
        self.evaluate_calls: list[UniverseSummary] = []

    def build_prompt(self, summary: UniverseSummary) -> str:
        return build_universe_evaluation_prompt(summary)

    def evaluate(self, summary: UniverseSummary) -> UniverseEvaluationOutput:
        self.evaluate_calls.append(summary)
        if self._error is not None:
            raise self._error
        return self._output


class FakeAIPortfolioAgent:
    """In-memory :class:`AIPortfolioAgent` returning canned structured output.

    Set ``build_error``/``rebalance_error`` to drive failure paths. ``build_calls``
    and ``rebalance_calls`` record the keyword arguments of each call so tests can
    assert the service passed flags (risk profile, allow_short, ...) through.

    ``research_queries`` simulates the agent doing web searches: each entry is
    emitted via :func:`note_web_search` when ``build``/``rebalance`` runs, so — since
    the service wraps the agent call in ``record_web_searches()`` — the run's
    research transcript is captured exactly as it would be with the real agent. The
    emission happens BEFORE any configured error is raised, mirroring how research
    performed mid-run survives a later failure.
    """

    def __init__(
        self,
        *,
        build_result: AIPortfolioBuildResult | None = None,
        rebalance_result: AIRebalanceResult | None = None,
        build_error: Exception | None = None,
        rebalance_error: Exception | None = None,
        research_queries: list[str] | None = None,
    ) -> None:
        self._build_result = build_result
        self._rebalance_result = rebalance_result
        self._build_error = build_error
        self._rebalance_error = rebalance_error
        self._research_queries = research_queries or []
        self.build_calls: list[dict[str, Any]] = []
        self.rebalance_calls: list[dict[str, Any]] = []

    def _emit_research(self) -> None:
        """Record each configured query as a web search on the active recorder."""
        for query in self._research_queries:
            note_web_search(
                query, {"organic_results": [{"title": f"result for {query}"}]}
            )

    def build(
        self,
        candidates: list[dict[str, Any]],
        risk_profile: str,
        guardrails: Any = None,
    ) -> AIPortfolioBuildResult:
        self.build_calls.append(
            {
                "candidates": candidates,
                "risk_profile": risk_profile,
                "guardrails": guardrails,
            }
        )
        self._emit_research()
        if self._build_error is not None:
            raise self._build_error
        assert self._build_result is not None, "FakeAIPortfolioAgent has no build_result"
        return self._build_result

    def rebalance(
        self,
        holdings: list[dict[str, Any]],
        account_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        risk_profile: str = "balanced",
        instructions: str = "",
        input_template: str = "",
        guardrails: Any = None,
        recent_outcomes: Any = None,
    ) -> AIRebalanceResult:
        self.rebalance_calls.append(
            {
                "holdings": holdings,
                "account_summary": account_summary,
                "candidates": candidates,
                "risk_profile": risk_profile,
                "instructions": instructions,
                "input_template": input_template,
                "guardrails": guardrails,
                "recent_outcomes": recent_outcomes,
            }
        )
        self._emit_research()
        if self._rebalance_error is not None:
            raise self._rebalance_error
        assert (
            self._rebalance_result is not None
        ), "FakeAIPortfolioAgent has no rebalance_result"
        return self._rebalance_result


class FakeBroker(StubBroker):
    """A :class:`StubBroker` with tunable asset-lookup behavior for add-time tests.

    Inherits the stub's full trading behavior and overrides only ``get_asset`` so
    tests can drive the authoritative tradability check:

    - ``not_tradable``: symbols returned as listed but *not* tradable.
    - ``not_found``: symbols the broker does not list at all (→ ``None``).
    - ``connection_error``: when set, every ``get_asset`` raises it, simulating an
      unconfigured/unreachable Alpaca (the hard-require 503 path).
    - ``fractionable``: symbols the broker reports as fractionable (overriding the
      stub default, which marks only crypto fractionable).
    - ``raise_for``: symbols whose individual ``get_asset`` raises, simulating a
      transient per-asset error (used by the fractionability backfill fail-open test).

    ``get_asset_calls`` records each ``(symbol, asset_class)`` for assertions.
    Symbols are compared case-insensitively. Without any knob set, behavior matches
    :class:`StubBroker` (tradable, dotted equities rejected).
    """

    def __init__(
        self,
        *,
        not_tradable: set[str] | None = None,
        not_found: set[str] | None = None,
        connection_error: ConnectionError | None = None,
        fractionable: set[str] | None = None,
        raise_for: set[str] | None = None,
        initial_cash: float = 100_000.0,
    ) -> None:
        super().__init__(initial_cash=initial_cash)
        self._not_tradable = {s.upper() for s in (not_tradable or set())}
        self._not_found = {s.upper() for s in (not_found or set())}
        self._connection_error = connection_error
        self._fractionable = {s.upper() for s in (fractionable or set())}
        self._raise_for = {s.upper() for s in (raise_for or set())}
        self.get_asset_calls: list[tuple[str, AssetClass]] = []

    def get_asset(
        self, symbol: str, asset_class: AssetClass = AssetClass.EQUITY
    ) -> BrokerAsset | None:
        self.get_asset_calls.append((symbol, asset_class))
        if self._connection_error is not None:
            raise self._connection_error
        key = symbol.upper()
        if key in self._raise_for:
            raise ConnectionError(f"transient lookup failure for {symbol}")
        if key in self._not_found:
            return None
        base = super().get_asset(symbol, asset_class)
        if base is None:
            return None
        fractionable = True if key in self._fractionable else base.fractionable
        tradable = key not in self._not_tradable
        if tradable == base.tradable and fractionable == base.fractionable:
            return base
        return BrokerAsset(
            symbol=base.symbol,
            asset_class=base.asset_class,
            tradable=tradable,
            fractionable=fractionable,
        )


class RecordingNotifier:
    """A :class:`~cadence.notify.base.Notifier` that records every send.

    Each call appends ``(message, title)`` to :attr:`sent` so tests can assert
    what a rebalance pushed. ``raises=True`` makes :meth:`send` raise, exercising
    the service's best-effort guard (a broken notifier must not fail a rebalance).
    ``result`` is the value returned on a normal (non-raising) send.
    """

    def __init__(self, *, raises: bool = False, result: bool = True) -> None:
        self._raises = raises
        self._result = result
        self.sent: list[tuple[str, str | None]] = []

    def send(self, message: str, *, title: str | None = None) -> bool:
        self.sent.append((message, title))
        if self._raises:
            raise RuntimeError("notifier boom")
        return self._result


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
