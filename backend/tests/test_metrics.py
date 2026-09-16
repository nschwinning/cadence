"""Unit tests for USD metric derivation using a fake provider (no network)."""

from __future__ import annotations

from datetime import date

import pytest
from tests.fakes import FakeMarketDataProvider

from cadence.assets.category import AssetCategory
from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.assets.metrics import derive_metrics
from cadence.assets.sector import Sector

_TODAY = date(2026, 1, 1)
_EARLIEST = date(2020, 1, 1)


def _history() -> list[HistoryBar]:
    # Three bars; each close*volume = 2_000_000 -> mean turnover = 2_000_000.
    return [
        HistoryBar(date=_EARLIEST, close=10.0, volume=200_000.0),
        HistoryBar(date=date(2023, 1, 1), close=10.0, volume=200_000.0),
        HistoryBar(date=date(2025, 12, 1), close=10.0, volume=200_000.0),
    ]


def test_derive_usd_asset_no_conversion() -> None:
    provider = FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Dollar Inc",
            exchange="NASDAQ",
            currency="USD",
            price=10.0,
            market_cap=2_000_000_000.0,
            quote_type="EQUITY",
        ),
        history=_history(),
    )

    derived = derive_metrics(provider, "USDI", today=_TODAY)

    assert derived.name == "Dollar Inc"
    assert derived.category is AssetCategory.STOCK
    assert derived.exchange == "NASDAQ"
    assert derived.currency == "USD"
    assert derived.metrics.price_usd == 10.0
    assert derived.metrics.market_cap_usd == 2_000_000_000.0
    assert derived.metrics.avg_daily_turnover_usd == 2_000_000.0
    expected_years = (_TODAY - _EARLIEST).days / 365.25
    assert derived.metrics.history_years == pytest.approx(expected_years)


def test_derive_non_usd_asset_is_converted() -> None:
    provider = FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Euro Corp",
            exchange="XETRA",
            currency="EUR",
            price=10.0,
            market_cap=2_000_000_000.0,
            quote_type="EQUITY",
        ),
        history=_history(),
        fx_rates={"EUR": 0.9},
    )

    derived = derive_metrics(provider, "EUCO", today=_TODAY)

    assert derived.currency == "EUR"
    assert derived.metrics.price_usd == pytest.approx(9.0)
    assert derived.metrics.market_cap_usd == pytest.approx(1_800_000_000.0)
    assert derived.metrics.avg_daily_turnover_usd == pytest.approx(1_800_000.0)


def test_derive_crypto_category() -> None:
    provider = FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Bitcoin USD",
            exchange="CCC",
            currency="USD",
            price=60_000.0,
            market_cap=1_000_000_000_000.0,
            quote_type="CRYPTOCURRENCY",
        ),
        history=_history(),
        fx_rates={"USD": 0.9},
    )

    derived = derive_metrics(provider, "BTC-USD", today=_TODAY)

    assert derived.category is AssetCategory.CRYPTO


def test_derive_missing_quote_type_falls_back_to_other() -> None:
    provider = FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Mystery",
            exchange="XXX",
            currency="USD",
            price=10.0,
            market_cap=2_000_000_000.0,
            quote_type=None,
        ),
        history=_history(),
    )

    derived = derive_metrics(provider, "MYST", today=_TODAY)

    assert derived.category is AssetCategory.OTHER


def test_derive_classifies_equity_sector_from_slug() -> None:
    provider = FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Big Bank",
            exchange="NYSE",
            currency="USD",
            price=100.0,
            market_cap=5_000_000_000.0,
            quote_type="EQUITY",
            sector="Financial Services",
            sector_key="financial-services",
        ),
        history=_history(),
    )

    derived = derive_metrics(provider, "BANK", today=_TODAY)

    assert derived.sector is Sector.FINANCIAL_SERVICES


def test_derive_missing_or_unknown_sector_is_none() -> None:
    provider = FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Bitcoin USD",
            exchange="CCC",
            currency="USD",
            price=60_000.0,
            market_cap=1_000_000_000_000.0,
            quote_type="CRYPTOCURRENCY",
            sector=None,
            sector_key=None,
        ),
        history=_history(),
    )

    derived = derive_metrics(provider, "BTC-USD", today=_TODAY)

    assert derived.sector is None
