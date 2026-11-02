"""Market-data seam for the strategy-bot tick (real-time ``feed=iex``).

The tick reads intraday bars through the :class:`MarketData` protocol so the data
source is swappable without touching strategy or engine code. The v1
implementation is :class:`RestMarketData`, which fetches bars from Alpaca's
market-data REST API with the **feed set explicitly** (default ``iex``, which is
real-time on the free tier — see the subsystem design). An unspecified feed would
fall back to the consolidated (SIP) feed, whose most recent ~15 minutes are
restricted on the free tier and would make the tick act on stale data.

Each read returns a :class:`BarsResult` carrying a freshness verdict: if the most
recent bar is older than the configured freshness bound (or no bar is returned at
all — IEX is a single exchange and may have no recent trade), ``fresh`` is
``False`` and the tick runner skips that session rather than trading a stale
signal.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast, runtime_checkable

import requests

from cadence.broker.alpaca import DATA_BASE_URL
from cadence.config import settings
from cadence.strategy_bots.strategy import Bar


@dataclass(frozen=True)
class BarsResult:
    """Bars for one symbol plus whether the most recent one is fresh enough.

    ``bars`` are ordered oldest→newest. ``as_of`` is the most recent bar's
    timestamp (``None`` when no bars were returned). ``fresh`` is ``True`` only
    when ``as_of`` is within the configured freshness bound of the tick time.
    """

    bars: list[Bar]
    as_of: datetime | None
    fresh: bool


@runtime_checkable
class MarketData(Protocol):
    """Source of recent bars for a symbol, with a freshness guarantee."""

    def latest_bars(
        self, symbol: str, timeframe: str, count: int, *, now: datetime
    ) -> BarsResult:
        """Return up to ``count`` most-recent bars and a freshness verdict."""
        ...


class _Session(Protocol):
    """Minimal ``requests``-compatible session for dependency injection."""

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        ...


def _parse_timestamp(value: str) -> datetime:
    """Parse an Alpaca ISO-8601 bar timestamp into an aware UTC datetime."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_bar(raw: Mapping[str, Any]) -> Bar:
    """Convert one Alpaca bar object (``t/o/h/l/c/v``) to a :class:`Bar`."""
    return Bar(
        timestamp=_parse_timestamp(raw["t"]),
        open=float(raw["o"]),
        high=float(raw["h"]),
        low=float(raw["l"]),
        close=float(raw["c"]),
        volume=float(raw.get("v", 0.0)),
    )


class RestMarketData:
    """Fetches bars from Alpaca market-data REST with an explicit feed.

    Credentials and the feed default to :data:`settings`; a ``requests``-style
    ``session`` can be injected so tests never touch the network.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        feed: str | None = None,
        freshness_minutes: int | None = None,
        session: _Session | None = None,
        base_url: str = DATA_BASE_URL,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.ALPACA_API_KEY
        self._secret_key = (
            secret_key if secret_key is not None else settings.ALPACA_SECRET_KEY
        )
        # Default to the configured feed; never leave it unset (that trips the
        # free-tier SIP restriction).
        self._feed = feed if feed is not None else settings.BOT_MARKET_DATA_FEED
        self._freshness = timedelta(
            minutes=freshness_minutes
            if freshness_minutes is not None
            else settings.BOT_BAR_FRESHNESS_MINUTES
        )
        self._session: _Session = session or cast("_Session", requests)
        self._base_url = base_url

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret_key,
        }

    def latest_bars(
        self, symbol: str, timeframe: str, count: int, *, now: datetime
    ) -> BarsResult:
        """Fetch the ``count`` most-recent ``timeframe`` bars for ``symbol``."""
        params = {
            "timeframe": timeframe,
            "limit": count,
            # Explicit, always — the whole point of the seam.
            "feed": self._feed,
            # Newest first so ``limit`` keeps the most recent bars.
            "sort": "desc",
        }
        response = self._session.request(
            "GET",
            f"{self._base_url}/v2/stocks/{symbol}/bars",
            headers=self._headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json() if response.text else {}
        raw_bars = payload.get("bars") or []
        bars = sorted(
            (_parse_bar(raw) for raw in raw_bars), key=lambda bar: bar.timestamp
        )
        as_of = bars[-1].timestamp if bars else None
        fresh = as_of is not None and (now - as_of) <= self._freshness
        return BarsResult(bars=bars, as_of=as_of, fresh=fresh)


class StubMarketData:
    """Deterministic offline bars (a flat series) for stub/Docker-smoke runs.

    Returns a flat price series so the MA Crossover strategy never crosses and the
    offline tick is a safe no-op (no orders). Tests that need a particular signal
    inject their own :class:`MarketData`.
    """

    def __init__(
        self, *, price: float = 100.0, freshness_minutes: int | None = None
    ) -> None:
        self._price = price
        self._interval = timedelta(minutes=5)

    def latest_bars(
        self, symbol: str, timeframe: str, count: int, *, now: datetime
    ) -> BarsResult:
        """Return ``count`` flat, fresh bars ending at ``now``."""
        bars = [
            Bar(
                timestamp=now - self._interval * (count - 1 - i),
                open=self._price,
                high=self._price,
                low=self._price,
                close=self._price,
                volume=1_000.0,
            )
            for i in range(count)
        ]
        as_of = bars[-1].timestamp if bars else None
        return BarsResult(bars=bars, as_of=as_of, fresh=True)


def get_market_data() -> MarketData:
    """Provide the market-data source. Overridden with a fake in tests.

    Returns :class:`StubMarketData` when ``ALPACA_STUB`` is set (offline/dev);
    otherwise the real :class:`RestMarketData` reading its feed from settings.
    """
    if settings.ALPACA_STUB:
        return StubMarketData()
    return RestMarketData()
