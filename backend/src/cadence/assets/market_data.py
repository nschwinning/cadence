"""Market data access behind a thin, testable interface.

All network access is confined to :class:`YFinanceMarketDataProvider`. The rest
of the domain depends only on the :class:`MarketDataProvider` protocol, so tests
inject a fake and never touch the network.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from cadence.assets.constants import DETAIL_HISTORY_TRADING_DAYS
from cadence.assets.errors import (
    MarketDataUnavailableError,
    UnknownTickerError,
)


@dataclass(frozen=True)
class AssetInfo:
    """Company/market snapshot for a ticker (in the native currency)."""

    company_name: str | None
    exchange: str | None
    currency: str
    price: float | None
    market_cap: float | None
    quote_type: str | None
    # Economic sector from the provider: ``sector`` is the display label
    # (e.g. "Financial Services"), ``sector_key`` the stable slug
    # (e.g. "financial-services"). Both are ``None`` when the provider reports
    # no sector (crypto, most ETFs/funds). The slug is authoritative for
    # classification; the label is carried for potential display reconciliation.
    sector: str | None = None
    sector_key: str | None = None
    # Stable company-profile fields persisted on the asset at add time. Each is
    # optional and defaults to ``None`` when the provider omits it, so a missing
    # field never fails the add.
    country: str | None = None
    city: str | None = None
    employees: int | None = None
    website: str | None = None


@dataclass(frozen=True)
class HistoryBar:
    """A single daily price bar.

    ``date``, ``close``, and ``volume`` are the long-standing fields used by the
    detail display and metrics. ``open``/``high``/``low`` and the
    split/dividend-adjusted ``adj_close`` are optional additions carrying the
    full OHLCV bar; they default to ``None`` so existing close-only constructors
    keep working.
    """

    date: date
    close: float
    volume: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    adj_close: float | None = None


@dataclass(frozen=True)
class AssetDetailData:
    """Native-currency detail snapshot for a ticker (no FX conversion).

    ``price_history`` reuses :class:`HistoryBar`; the volume field is ignored
    when serializing the details view (only ``date`` and ``close`` are used).

    The ``country``/``city``/``employees``/``website``/``volume``/``avg_volume``
    fields back the Company Information panel; each is optional and defaults to
    ``None`` when the provider does not supply it, so a missing field never
    fails the fetch.
    """

    current_price: float | None
    previous_close: float | None
    short_description: str | None
    price_history: list[HistoryBar]
    country: str | None = None
    city: str | None = None
    employees: int | None = None
    website: str | None = None
    volume: int | None = None
    avg_volume: int | None = None


@runtime_checkable
class MarketDataProvider(Protocol):
    """Interface for fetching company info, price history, and FX rates."""

    def fetch_info(self, ticker: str) -> AssetInfo:
        """Return company/market info for ``ticker``.

        Raises:
            UnknownTickerError: if the provider has no data for the ticker.
            MarketDataUnavailableError: on provider/network failure.
        """
        ...

    def fetch_history(self, ticker: str) -> list[HistoryBar]:
        """Return the daily price history (ascending by date) for ``ticker``.

        Raises:
            UnknownTickerError: if the provider has no history for the ticker.
            MarketDataUnavailableError: on provider/network failure.
        """
        ...

    def fetch_fx_rate(self, currency: str) -> float:
        """Return the ``currency`` -> USD conversion rate (1.0 for USD).

        Raises:
            MarketDataUnavailableError: if the rate cannot be obtained.
        """
        ...

    def fetch_detail(self, ticker: str) -> AssetDetailData:
        """Return native-currency detail data for ``ticker`` (no FX).

        Raises:
            UnknownTickerError: if the provider has no data for the ticker.
            MarketDataUnavailableError: on provider/network failure.
        """
        ...


class YFinanceMarketDataProvider:
    """yfinance-backed :class:`MarketDataProvider` implementation."""

    def fetch_info(self, ticker: str) -> AssetInfo:
        import yfinance as yf

        try:
            raw = yf.Ticker(ticker).info
        except Exception as exc:
            raise MarketDataUnavailableError(
                f"Could not fetch info for {ticker!r}"
            ) from exc

        if not raw or not self._has_usable_info(raw):
            raise UnknownTickerError(f"No usable data for ticker {ticker!r}")

        currency = raw.get("currency")
        if not currency:
            raise UnknownTickerError(f"No currency for ticker {ticker!r}")

        quote_type = raw.get("quoteType")
        sector = raw.get("sector")
        sector_key = raw.get("sectorKey")

        return AssetInfo(
            company_name=raw.get("longName") or raw.get("shortName"),
            exchange=raw.get("exchange"),
            currency=str(currency).upper(),
            price=self._as_float(
                raw.get("currentPrice")
                or raw.get("regularMarketPrice")
                or raw.get("previousClose")
            ),
            market_cap=self._as_float(raw.get("marketCap")),
            quote_type=str(quote_type) if quote_type is not None else None,
            sector=str(sector) if sector is not None else None,
            sector_key=str(sector_key) if sector_key is not None else None,
            country=raw.get("country"),
            city=raw.get("city"),
            employees=self._as_int(raw.get("fullTimeEmployees")),
            website=raw.get("website"),
        )

    def fetch_history(self, ticker: str) -> list[HistoryBar]:
        import yfinance as yf

        try:
            frame = yf.Ticker(ticker).history(period="max", auto_adjust=False)
        except Exception as exc:
            raise MarketDataUnavailableError(
                f"Could not fetch history for {ticker!r}"
            ) from exc

        if frame is None or frame.empty:
            raise UnknownTickerError(f"No history for ticker {ticker!r}")

        bars: list[HistoryBar] = []
        for index, row in frame.iterrows():
            close = self._as_float(row.get("Close"))
            volume = self._as_float(row.get("Volume"))
            if close is None or volume is None:
                continue
            # ``auto_adjust=False`` keeps raw OHLC and exposes "Adj Close"
            # alongside; retain the full bar.
            bars.append(
                HistoryBar(
                    date=index.date(),
                    close=close,
                    volume=volume,
                    open=self._as_float(row.get("Open")),
                    high=self._as_float(row.get("High")),
                    low=self._as_float(row.get("Low")),
                    adj_close=self._as_float(row.get("Adj Close")),
                )
            )

        if not bars:
            raise UnknownTickerError(f"No usable history for ticker {ticker!r}")

        bars.sort(key=lambda bar: bar.date)
        return bars

    def fetch_fx_rate(self, currency: str) -> float:
        currency = currency.upper()
        if currency == "USD":
            return 1.0

        import yfinance as yf

        pair = f"{currency}USD=X"
        try:
            frame = yf.Ticker(pair).history(period="5d", auto_adjust=False)
        except Exception as exc:
            raise MarketDataUnavailableError(
                f"Could not fetch FX rate for {currency}"
            ) from exc

        if frame is None or frame.empty:
            raise MarketDataUnavailableError(
                f"No FX rate available for {currency}"
            )

        rate = self._as_float(frame["Close"].iloc[-1])
        if rate is None or rate <= 0:
            raise MarketDataUnavailableError(
                f"Invalid FX rate for {currency}"
            )
        return rate

    def fetch_detail(self, ticker: str) -> AssetDetailData:
        import yfinance as yf

        handle = yf.Ticker(ticker)

        try:
            raw = handle.info
        except Exception as exc:
            raise MarketDataUnavailableError(
                f"Could not fetch detail for {ticker!r}"
            ) from exc

        if not raw or not self._has_usable_info(raw):
            raise UnknownTickerError(f"No usable data for ticker {ticker!r}")

        try:
            frame = handle.history(period="max", auto_adjust=False)
        except Exception as exc:
            raise MarketDataUnavailableError(
                f"Could not fetch detail history for {ticker!r}"
            ) from exc

        if frame is None or frame.empty:
            raise UnknownTickerError(f"No history for ticker {ticker!r}")

        bars: list[HistoryBar] = []
        for index, row in frame.iterrows():
            close = self._as_float(row.get("Close"))
            volume = self._as_float(row.get("Volume"))
            if close is None:
                continue
            bars.append(
                HistoryBar(date=index.date(), close=close, volume=volume or 0.0)
            )

        if not bars:
            raise UnknownTickerError(f"No usable history for ticker {ticker!r}")

        bars.sort(key=lambda bar: bar.date)
        price_history = bars[-DETAIL_HISTORY_TRADING_DAYS:]

        return AssetDetailData(
            current_price=self._as_float(
                raw.get("currentPrice") or raw.get("regularMarketPrice")
            ),
            previous_close=self._as_float(raw.get("previousClose")),
            short_description=raw.get("longBusinessSummary"),
            price_history=price_history,
            country=raw.get("country"),
            city=raw.get("city"),
            employees=self._as_int(raw.get("fullTimeEmployees")),
            website=raw.get("website"),
            volume=self._as_int(
                raw.get("volume") or raw.get("regularMarketVolume")
            ),
            avg_volume=self._as_int(raw.get("averageVolume")),
        )

    @staticmethod
    def _has_usable_info(raw: dict[str, object]) -> bool:
        return any(
            raw.get(key) is not None
            for key in ("currentPrice", "regularMarketPrice", "previousClose")
        )

    @staticmethod
    def _as_float(value: object) -> float | None:
        if value is None:
            return None
        try:
            result = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if math.isnan(result):
            return None
        return result

    @classmethod
    def _as_int(cls, value: object) -> int | None:
        """Coerce a provider count (employees, volume) to ``int``.

        Routes through :meth:`_as_float` so NaN and unparseable values become
        ``None`` rather than raising; a valid number is truncated to ``int``.
        """
        result = cls._as_float(value)
        if result is None:
            return None
        return int(result)
