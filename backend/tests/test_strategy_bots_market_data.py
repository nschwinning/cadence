"""Unit tests for the strategy-bot market-data seam (explicit ``feed=iex``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cadence.strategy_bots.market_data import (
    MarketData,
    RestMarketData,
    StubMarketData,
)

_NOW = datetime(2026, 1, 2, 20, 0, tzinfo=UTC)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.text = "{}"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    """Captures the request params and returns a canned bars payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.last_params: dict[str, Any] | None = None
        self.last_url: str | None = None

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.last_url = url
        self.last_params = kwargs.get("params")
        return _FakeResponse(self._payload)


def _bar(ts: datetime, close: float) -> dict[str, Any]:
    return {
        "t": ts.isoformat().replace("+00:00", "Z"),
        "o": close,
        "h": close,
        "l": close,
        "c": close,
        "v": 1000,
    }


def test_rest_market_data_sends_feed_iex_and_returns_bars() -> None:
    payload = {
        "bars": [
            _bar(_NOW - timedelta(minutes=10), 101.0),
            _bar(_NOW - timedelta(minutes=5), 102.0),
            _bar(_NOW, 103.0),
        ]
    }
    session = _FakeSession(payload)
    source = RestMarketData(
        api_key="k",
        secret_key="s",
        feed="iex",
        freshness_minutes=10,
        session=session,
    )

    result = source.latest_bars("AAPL", "5Min", 3, now=_NOW)

    assert session.last_params is not None
    assert session.last_params["feed"] == "iex"
    assert "AAPL" in (session.last_url or "")
    # Bars returned oldest -> newest.
    assert [bar.close for bar in result.bars] == [101.0, 102.0, 103.0]
    assert result.as_of == _NOW
    assert result.fresh is True


def test_rest_market_data_reports_stale_most_recent_bar_as_unavailable() -> None:
    # Most recent bar is 30 minutes old but the freshness bound is 10 minutes.
    payload = {"bars": [_bar(_NOW - timedelta(minutes=30), 100.0)]}
    session = _FakeSession(payload)
    source = RestMarketData(
        api_key="k",
        secret_key="s",
        feed="iex",
        freshness_minutes=10,
        session=session,
    )

    result = source.latest_bars("AAPL", "5Min", 1, now=_NOW)

    assert result.bars  # bars were returned
    assert result.fresh is False  # but not fresh enough to act on


def test_rest_market_data_empty_payload_is_not_fresh() -> None:
    session = _FakeSession({"bars": []})
    source = RestMarketData(
        api_key="k", secret_key="s", feed="iex", freshness_minutes=10, session=session
    )

    result = source.latest_bars("AAPL", "5Min", 5, now=_NOW)

    assert result.bars == []
    assert result.as_of is None
    assert result.fresh is False


def test_stub_market_data_returns_fresh_flat_bars() -> None:
    source: MarketData = StubMarketData(price=100.0)

    result = source.latest_bars("AAPL", "5Min", 4, now=_NOW)

    assert len(result.bars) == 4
    assert {bar.close for bar in result.bars} == {100.0}
    assert result.fresh is True
    assert result.as_of == _NOW
