"""Sentiment scoring behind a thin, testable Protocol.

All network access to the sentiment sidecar is confined to
:class:`HttpSentimentScorer`. The rest of the domain depends only on the
:class:`SentimentScorer` protocol, so tests inject a stub and never touch the
network. Scoring is deliberately best-effort: an unset URL, an unreachable
service, or a malformed response yields an empty result (``[]``) rather than
raising, so the aggregation above it degrades to "sentiment unavailable".
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import httpx

from cadence.config import settings
from cadence.news_sentiment.models import SentimentScore

logger = logging.getLogger(__name__)


@runtime_checkable
class SentimentScorer(Protocol):
    """Seam for scoring financial text into tone probabilities.

    Implemented by :class:`HttpSentimentScorer` in production and by a fake in
    tests. ``score`` is synchronous (the services stay fully sync) and NEVER
    raises: a failed scoring returns an empty list, which the caller treats as
    "no usable sentiment". A successful call returns one :class:`SentimentScore`
    per input text, in order.
    """

    def score(self, texts: Sequence[str]) -> list[SentimentScore]:
        """Return a tone score per input text (never raises; ``[]`` on failure)."""
        ...


class HttpSentimentScorer:
    """Production :class:`SentimentScorer` — a thin client of the sentiment sidecar.

    Confines all HTTP to this class and never raises: any failure (unset URL,
    connection error, bad status, malformed body, or a length mismatch) degrades
    to an empty list and is logged. The sidecar scores a batch of texts and
    returns per-text ``positive``/``neutral``/``negative`` probabilities.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float | None = None,
    ) -> None:
        self._base_url = (
            base_url if base_url is not None else settings.SENTIMENT_SERVICE_URL
        ).rstrip("/")
        self._timeout = (
            timeout
            if timeout is not None
            else settings.SENTIMENT_SERVICE_TIMEOUT_SECONDS
        )

    def score(self, texts: Sequence[str]) -> list[SentimentScore]:
        items = list(texts)
        if not self._base_url or not items:
            return []
        try:
            response = httpx.post(
                f"{self._base_url}/score",
                json={"texts": items},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("sentiment scoring failed: %s", exc)
            return []
        return self._parse(payload, expected=len(items))

    @staticmethod
    def _parse(payload: object, *, expected: int) -> list[SentimentScore]:
        """Map the sidecar response into scores, or ``[]`` on any shape mismatch."""
        rows = payload.get("scores") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or len(rows) != expected:
            logger.warning("sentiment response shape mismatch (expected %d)", expected)
            return []
        scores: list[SentimentScore] = []
        for row in rows:
            if not isinstance(row, dict):
                return []
            try:
                scores.append(
                    SentimentScore(
                        positive=float(row["positive"]),
                        neutral=float(row["neutral"]),
                        negative=float(row["negative"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                return []
        return scores
