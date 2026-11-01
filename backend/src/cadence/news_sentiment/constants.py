"""Enums and the clock seam for the news-sentiment capability.

Tunable knobs (service URL, trailing-window length, recency half-life, neutral
band, article cap) live in :mod:`cadence.config` as settings; this module holds
only the deterministic, non-configurable definitions — the clock seam and the
small enums the resolved tone block uses.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

#: Timezone the sentiment "today" is anchored to (US market close), matching the
#: rebalance clock — the single seam for the as-of date.
MARKET_TZ = ZoneInfo("America/New_York")


def today() -> date:
    """Today's calendar date in the market-close timezone (tz-aware clock seam)."""
    return datetime.now(tz=MARKET_TZ).date()


class SentimentTone(StrEnum):
    """Human-readable leaning of a ticker's aggregate tone."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class SentimentStatus(StrEnum):
    """Resolution status of a per-ticker sentiment block handed to the agent."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
