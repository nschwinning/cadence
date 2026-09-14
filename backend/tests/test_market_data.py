"""Unit tests for the yfinance provider's payload parsing (no network).

``yfinance.Ticker`` is monkeypatched so the ``.info`` payload is a canned dict;
this asserts how :class:`YFinanceMarketDataProvider` reads fields off it —
in particular that the economic sector slug is captured from ``sectorKey``.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from cadence.assets.market_data import YFinanceMarketDataProvider


class _FakeTicker:
    def __init__(
        self, info: dict[str, object], history: pd.DataFrame | None = None
    ) -> None:
        self.info = info
        self._history = history

    def history(self, *args: object, **kwargs: object) -> pd.DataFrame:
        assert self._history is not None
        return self._history


def _patch_ticker(monkeypatch, info: dict[str, object]) -> None:
    monkeypatch.setattr(yf, "Ticker", lambda ticker: _FakeTicker(info))


def test_fetch_info_reads_sector_slug_and_label(monkeypatch) -> None:
    _patch_ticker(
        monkeypatch,
        {
            "currency": "USD",
            "regularMarketPrice": 190.0,
            "quoteType": "EQUITY",
            "sector": "Financial Services",
            "sectorKey": "financial-services",
        },
    )

    info = YFinanceMarketDataProvider().fetch_info("JPM")

    assert info.sector_key == "financial-services"
    assert info.sector == "Financial Services"


def test_fetch_info_missing_sector_is_none(monkeypatch) -> None:
    _patch_ticker(
        monkeypatch,
        {
            "currency": "USD",
            "regularMarketPrice": 60_000.0,
            "quoteType": "CRYPTOCURRENCY",
        },
    )

    info = YFinanceMarketDataProvider().fetch_info("BTC-USD")

    assert info.sector_key is None
    assert info.sector is None


def test_fetch_info_maps_company_profile_fields(monkeypatch) -> None:
    _patch_ticker(
        monkeypatch,
        {
            "currency": "USD",
            "regularMarketPrice": 190.0,
            "quoteType": "EQUITY",
            "country": "United States",
            "city": "Cupertino",
            "fullTimeEmployees": 164_000,
            "website": "https://apple.com",
        },
    )

    info = YFinanceMarketDataProvider().fetch_info("AAPL")

    assert info.country == "United States"
    assert info.city == "Cupertino"
    assert info.employees == 164_000  # fullTimeEmployees -> employees
    assert info.website == "https://apple.com"


def test_fetch_info_missing_company_profile_fields_are_none(monkeypatch) -> None:
    _patch_ticker(
        monkeypatch,
        {
            "currency": "USD",
            "regularMarketPrice": 190.0,
            "quoteType": "EQUITY",
        },
    )

    info = YFinanceMarketDataProvider().fetch_info("AAPL")

    assert info.country is None
    assert info.city is None
    assert info.employees is None
    assert info.website is None


def _detail_history_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Close": [11.5, 12.5],
            "Volume": [1000.0, 2000.0],
        },
        index=pd.to_datetime(["2020-01-02", "2020-01-03"]),
    )


def test_fetch_detail_maps_company_information_fields(monkeypatch) -> None:
    info = {
        "currency": "USD",
        "currentPrice": 190.0,
        "previousClose": 188.0,
        "longBusinessSummary": "Makes things.",
        "country": "United States",
        "city": "Cupertino",
        "fullTimeEmployees": 164_000,
        "website": "https://apple.com",
        "regularMarketVolume": 52_140_300,
        "averageVolume": 58_910_000,
    }
    monkeypatch.setattr(
        yf,
        "Ticker",
        lambda ticker: _FakeTicker(info=info, history=_detail_history_frame()),
    )

    detail = YFinanceMarketDataProvider().fetch_detail("AAPL")

    assert detail.country == "United States"
    assert detail.city == "Cupertino"
    assert detail.employees == 164_000
    assert detail.website == "https://apple.com"
    assert detail.volume == 52_140_300
    assert detail.avg_volume == 58_910_000


def test_fetch_detail_missing_company_fields_are_none(monkeypatch) -> None:
    info = {
        "currency": "USD",
        "currentPrice": 190.0,
        "previousClose": 188.0,
    }
    monkeypatch.setattr(
        yf,
        "Ticker",
        lambda ticker: _FakeTicker(info=info, history=_detail_history_frame()),
    )

    detail = YFinanceMarketDataProvider().fetch_detail("AAPL")

    assert detail.country is None
    assert detail.city is None
    assert detail.employees is None
    assert detail.website is None
    assert detail.volume is None
    assert detail.avg_volume is None


def test_fetch_history_reads_full_ohlcv_bar(monkeypatch) -> None:
    frame = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [12.0, 13.0],
            "Low": [9.0, 10.5],
            "Close": [11.5, 12.5],
            "Adj Close": [5.75, 12.5],
            "Volume": [1000.0, 2000.0],
        },
        index=pd.to_datetime(["2020-01-02", "2020-01-03"]),
    )
    monkeypatch.setattr(
        yf, "Ticker", lambda ticker: _FakeTicker(info={}, history=frame)
    )

    bars = YFinanceMarketDataProvider().fetch_history("AAPL")

    assert len(bars) == 2
    first = bars[0]
    assert first.date.isoformat() == "2020-01-02"
    assert first.open == 10.0
    assert first.high == 12.0
    assert first.low == 9.0
    assert first.close == 11.5
    assert first.adj_close == 5.75
    assert first.volume == 1000.0
