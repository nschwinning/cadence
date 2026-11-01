"""News-sentiment aggregation, caching, and annotation resolution.

The rebalance flow resolves per-ticker sentiment annotations through
:func:`resolve_sentiment_annotations`, which fetches each ticker's recent news,
scores it through the sentiment sidecar, aggregates a recency-weighted tone, and
yields an explicit "unavailable" marker rather than ever fabricating a signal or
raising. Computed signals are cached in process keyed by ``(ticker, date)`` so the
two resolve passes a rebalance makes (candidates, then holdings) reuse one scoring
pass per ticker-day rather than re-scoring.

The feature is strictly additive and non-blocking: an unset service URL, an
unreachable sidecar or news source, a scoring error, or a ticker with no news all
degrade to "sentiment unavailable" for the affected tickers, and the sentiment
path never fails a rebalance.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date
from typing import Any

from cadence.config import settings
from cadence.news_sentiment import constants as c
from cadence.news_sentiment.constants import SentimentStatus, SentimentTone
from cadence.news_sentiment.models import NewsItem, SentimentScore, SentimentSignal
from cadence.news_sentiment.news import AlpacaNewsSource, NewsSource, window_start
from cadence.news_sentiment.scorer import HttpSentimentScorer, SentimentScorer

logger = logging.getLogger(__name__)

#: In-process cache of resolved signals keyed by ``(ticker, as_of.isoformat())``.
#: Scoped by date, so same-day repeat reads (candidates then holdings in one
#: rebalance) reuse the result instead of re-scoring. Cleared between tests.
_SIGNAL_CACHE: dict[tuple[str, str], SentimentSignal] = {}


def clear_signal_cache() -> None:
    """Drop every cached signal (used by tests for isolation)."""
    _SIGNAL_CACHE.clear()


def _default_scorer() -> SentimentScorer:
    """The production scorer, built from live settings."""
    return HttpSentimentScorer()


def _default_news_source() -> NewsSource:
    """The production news source, built from live settings."""
    return AlpacaNewsSource()


def _recency_weight(item: NewsItem, as_of: date, halflife_days: float) -> float:
    """Exponential-decay weight for one item given its age relative to ``as_of``.

    An item published on (or after) ``as_of`` carries full weight 1.0; each
    ``halflife_days`` of age halves the weight. Deterministic given the inputs.
    """
    age_days = (as_of - item.published_at.astimezone(c.MARKET_TZ).date()).days
    age_days = max(age_days, 0)
    if halflife_days <= 0:
        return 1.0
    return float(0.5 ** (age_days / halflife_days))


def _classify(score: float, neutral_band: float) -> SentimentTone:
    """Classify a ``positive − negative`` aggregate into a tone leaning."""
    if score > neutral_band:
        return SentimentTone.POSITIVE
    if score < -neutral_band:
        return SentimentTone.NEGATIVE
    return SentimentTone.NEUTRAL


def aggregate_signal(
    ticker: str,
    items: Sequence[NewsItem],
    scores: Sequence[SentimentScore],
    as_of: date,
    *,
    halflife_days: float | None = None,
    neutral_band: float | None = None,
) -> SentimentSignal:
    """Aggregate scored news into a recency-weighted tone signal (deterministic).

    The aggregate is the recency-weighted mean of each item's
    ``positive − negative`` polarity, carried with the article count and classified
    into a positive / neutral / negative leaning. With no items, no scores, a
    length mismatch, or a degenerate zero weight-sum, yields "unavailable".
    """
    halflife = (
        halflife_days
        if halflife_days is not None
        else settings.SENTIMENT_RECENCY_HALFLIFE_DAYS
    )
    band = neutral_band if neutral_band is not None else settings.SENTIMENT_NEUTRAL_BAND
    if not items or len(scores) != len(items):
        return SentimentSignal.unavailable(ticker, as_of)
    weighted_sum = 0.0
    weight_total = 0.0
    for item, score in zip(items, scores, strict=True):
        weight = _recency_weight(item, as_of, halflife)
        weighted_sum += weight * score.polarity
        weight_total += weight
    if weight_total <= 0:
        return SentimentSignal.unavailable(ticker, as_of)
    aggregate = weighted_sum / weight_total
    return SentimentSignal(
        ticker=ticker,
        status=SentimentStatus.AVAILABLE,
        as_of=as_of,
        tone=_classify(aggregate, band),
        score=aggregate,
        article_count=len(items),
    )


def _resolve_one(
    ticker: str,
    as_of: date,
    scorer: SentimentScorer,
    news_source: NewsSource,
) -> SentimentSignal:
    """Resolve one ticker's signal (cached), degrading to unavailable on any issue."""
    cache_key = (ticker, as_of.isoformat())
    cached = _SIGNAL_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        start = window_start(as_of, settings.SENTIMENT_WINDOW_DAYS)
        items = news_source.fetch_news(
            ticker, start=start, limit=settings.SENTIMENT_MAX_ARTICLES
        )
        if not items:
            signal = SentimentSignal.unavailable(ticker, as_of)
        else:
            scores = scorer.score([item.text() for item in items])
            signal = aggregate_signal(ticker, items, scores, as_of)
    except Exception:  # sentiment is strictly additive, never fatal to a rebalance
        logger.exception("sentiment resolution failed for %s", ticker)
        signal = SentimentSignal.unavailable(ticker, as_of)
    _SIGNAL_CACHE[cache_key] = signal
    return signal


def resolve_sentiment_annotations(
    tickers: Sequence[str],
    *,
    scorer: SentimentScorer | None = None,
    news_source: NewsSource | None = None,
    as_of: date | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve a ticker→annotation map, degrading per ticker to "unavailable".

    When ``scorer`` is not injected and the sentiment service URL is unset, the
    feature is disabled and every ticker resolves to "unavailable" without any
    network call. Otherwise each ticker is resolved independently, so a partial
    batch (some tickers with news, some without) yields available signals for the
    former and the unavailable marker for the latter. Never raises.
    """
    as_of = as_of or c.today()
    # Deduplicate while preserving first-seen order.
    unique = list(dict.fromkeys(tickers))
    use_default_scorer = scorer is None
    if use_default_scorer and not settings.SENTIMENT_SERVICE_URL:
        return {
            ticker: SentimentSignal.unavailable(ticker, as_of).annotation()
            for ticker in unique
        }
    resolved_scorer = scorer if scorer is not None else _default_scorer()
    resolved_news = (
        news_source if news_source is not None else _default_news_source()
    )
    return {
        ticker: _resolve_one(ticker, as_of, resolved_scorer, resolved_news).annotation()
        for ticker in unique
    }
