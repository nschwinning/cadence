"""A deterministic, offline stand-in for the recommender agent.

Enabled only when ``RECOMMENDER_STUB`` is set. It makes no network calls and
proposes a canned pool of well-known, liquid large-cap tickers per requested
category. Every proposal still flows through the real server-side eligibility
re-validation (:func:`cadence.assets.service.add_asset`), so an end-to-end
smoke can exercise the full create -> validate -> add pipeline without an
OpenAI or SerpAPI key. Production behavior is unchanged: the default agent still
requires ``OPENAI_API_KEY`` and fails cleanly when it is missing.
"""

from __future__ import annotations

from cadence.recommendations.agent import (
    EligibilityCriteria,
    RecommendationCandidate,
    RecommendationOutput,
    RecommendationResult,
    build_recommendation_prompt,
)
from cadence.recommendations.composition import UniverseComposition

#: Canned, liquid large-cap tickers per category. Chosen to comfortably clear
#: the eligibility thresholds so the smoke actually adds assets.
_CANNED_TICKERS: dict[str, list[str]] = {
    "stock": ["NVDA", "GOOGL", "AMZN", "META", "JPM", "V", "JNJ", "WMT", "PG", "MA"],
    "etf": ["SPY", "QQQ", "VOO", "IVV", "VTI"],
    "crypto": ["BTC-USD", "ETH-USD"],
}

#: Categories without a dedicated pool fall back to the stock pool.
_FALLBACK_CATEGORY = "stock"


class StubRecommenderAgent:
    """Offline :class:`RecommenderAgent` returning canned candidates."""

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
        tickers = self._pool_for(categories)
        candidates = [
            RecommendationCandidate(
                ticker=ticker,
                rationale="Stub proposal: large-cap, liquid, long-listed.",
            )
            for ticker in tickers
        ]
        output = RecommendationOutput(candidates=candidates)
        # Simulate one web_search per candidate so the recorded tool-call count
        # on the run row is meaningful during the smoke.
        return RecommendationResult(output=output, tool_call_count=len(candidates))

    def _pool_for(self, categories: list[str]) -> list[str]:
        """Union the canned pools for the requested categories, order-preserving."""
        requested = categories or [_FALLBACK_CATEGORY]
        seen: set[str] = set()
        pool: list[str] = []
        for category in requested:
            for ticker in _CANNED_TICKERS.get(category, _CANNED_TICKERS[_FALLBACK_CATEGORY]):
                if ticker not in seen:
                    seen.add(ticker)
                    pool.append(ticker)
        return pool
