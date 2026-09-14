"""Derive EUR-normalized asset metrics from provider data.

This layer orchestrates the (network-bound) provider but contains only pure
arithmetic itself, so it is unit-tested with a fake provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from cadence.assets.category import AssetCategory, categorize
from cadence.assets.constants import TURNOVER_WINDOW_TRADING_DAYS
from cadence.assets.errors import MarketDataUnavailableError
from cadence.assets.evaluation import AssetMetrics
from cadence.assets.market_data import HistoryBar, MarketDataProvider
from cadence.assets.sector import Sector, classify_sector

_DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class DerivedAsset:
    """Everything needed to persist and evaluate an asset, in EUR."""

    name: str | None
    category: AssetCategory
    sector: Sector | None
    exchange: str | None
    currency: str
    # Stable company-profile fields carried through from the provider info and
    # persisted on the asset at add time; each optional (``None`` when omitted).
    country: str | None
    city: str | None
    employees: int | None
    website: str | None
    metrics: AssetMetrics


def derive_metrics(
    provider: MarketDataProvider,
    ticker: str,
    *,
    today: date | None = None,
) -> DerivedAsset:
    """Fetch, convert to EUR, and derive metrics for ``ticker``.

    Raises:
        UnknownTickerError: propagated from the provider for unknown tickers.
        MarketDataUnavailableError: on provider/FX failure.
    """
    reference_day = today or datetime.now(tz=UTC).date()

    info = provider.fetch_info(ticker)
    history = provider.fetch_history(ticker)

    fx_rate = provider.fetch_fx_rate(info.currency)

    price_eur = _convert(info.price, fx_rate)
    market_cap_eur = _convert(info.market_cap, fx_rate)
    turnover_native = _avg_daily_turnover(history)
    avg_daily_turnover_eur = _convert(turnover_native, fx_rate)
    history_years = _history_years(history, reference_day)

    return DerivedAsset(
        name=info.company_name,
        category=categorize(info.quote_type),
        sector=classify_sector(info.sector_key),
        exchange=info.exchange,
        currency=info.currency,
        country=info.country,
        city=info.city,
        employees=info.employees,
        website=info.website,
        metrics=AssetMetrics(
            price_eur=price_eur,
            avg_daily_turnover_eur=avg_daily_turnover_eur,
            market_cap_eur=market_cap_eur,
            history_years=history_years,
        ),
    )


def _convert(value: float | None, fx_rate: float) -> float | None:
    if value is None:
        return None
    return value * fx_rate


def _avg_daily_turnover(history: list[HistoryBar]) -> float | None:
    """Mean of daily (close * volume) over the trailing turnover window."""
    if not history:
        return None
    window = history[-TURNOVER_WINDOW_TRADING_DAYS:]
    if not window:
        return None
    total = sum(bar.close * bar.volume for bar in window)
    return total / len(window)


def _history_years(history: list[HistoryBar], reference_day: date) -> float | None:
    """Years between the earliest available bar and the reference day."""
    if not history:
        return None
    earliest = min(bar.date for bar in history)
    days = (reference_day - earliest).days
    if days < 0:
        raise MarketDataUnavailableError("History starts in the future")
    return days / _DAYS_PER_YEAR
