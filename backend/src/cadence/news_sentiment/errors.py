"""Exceptions for the news-sentiment capability.

These are internal signals only: the public resolution path degrades to an
explicit "sentiment unavailable" marker and never propagates an error to the
rebalance flow (see :mod:`cadence.news_sentiment.service`).
"""

from __future__ import annotations


class NewsSentimentError(Exception):
    """Base class for news-sentiment errors."""


class SentimentServiceError(NewsSentimentError):
    """The sentiment-scoring sidecar was unreachable or returned a bad response."""


class NewsSourceError(NewsSentimentError):
    """The news source was unreachable or returned a bad response."""
