"""Tests for :class:`AlpacaBroker` using a fake ``requests`` session.

No real network calls are made: a fake session records requests and returns
canned JSON, letting us assert URL/auth selection and response parsing.
"""

from __future__ import annotations

from typing import Any

import pytest

from cadence.broker import AlpacaBroker
from cadence.broker.base import ConnectionError
from cadence.broker.models import AssetClass, OrderSide, OrderStatus, OrderType


class FakeResponse:
    """Minimal stand-in for a ``requests.Response``."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.text = "{}" if payload is not None else ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class FakeSession:
    """Records calls and returns queued/mapped canned responses."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        # Keyed by (method, endpoint-suffix) -> payload.
        self._routes = routes
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        for (route_method, suffix), payload in self._routes.items():
            if route_method == method and url.endswith(suffix):
                return FakeResponse(payload)
        raise AssertionError(f"Unexpected request: {method} {url}")


def _make_broker(routes: dict[tuple[str, str], Any]) -> tuple[AlpacaBroker, FakeSession]:
    session = FakeSession(routes)
    broker = AlpacaBroker(
        api_key="test-key",
        secret_key="test-secret",
        paper=True,
        session=session,
    )
    return broker, session


def test_missing_api_key_raises() -> None:
    with pytest.raises(ConnectionError):
        AlpacaBroker(api_key="", secret_key="secret", session=object())


def test_blank_secret_key_raises() -> None:
    with pytest.raises(ConnectionError):
        AlpacaBroker(api_key="key", secret_key="   ", session=object())


def test_paper_selects_paper_base_url() -> None:
    broker, session = _make_broker({("GET", "/v2/clock"): {"is_open": True}})
    broker.is_market_open()
    assert session.calls[0]["url"].startswith("https://paper-api.alpaca.markets")


def test_live_selects_live_base_url() -> None:
    session = FakeSession({("GET", "/v2/clock"): {"is_open": False}})
    broker = AlpacaBroker(
        api_key="k", secret_key="s", paper=False, session=session
    )
    broker.is_market_open()
    assert session.calls[0]["url"].startswith("https://api.alpaca.markets")


def test_auth_headers_are_sent() -> None:
    broker, session = _make_broker({("GET", "/v2/clock"): {"is_open": True}})
    broker.is_market_open()
    headers = session.calls[0]["headers"]
    assert headers["APCA-API-KEY-ID"] == "test-key"
    assert headers["APCA-API-SECRET-KEY"] == "test-secret"


def test_is_market_open_reads_clock() -> None:
    broker, _ = _make_broker({("GET", "/v2/clock"): {"is_open": True}})
    assert broker.is_market_open() is True

    broker2, _ = _make_broker({("GET", "/v2/clock"): {"is_open": False}})
    assert broker2.is_market_open() is False


def test_submit_order_maps_response_to_order() -> None:
    order_response = {
        "id": "abc-123",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "type": "market",
        "time_in_force": "day",
        "status": "filled",
        "submitted_at": "2026-09-14T10:00:00Z",
        "filled_qty": "10",
        "filled_avg_price": "150.25",
    }
    broker, session = _make_broker({("POST", "/v2/orders"): order_response})

    order = broker.buy("AAPL", 10)

    assert order.order_id == "abc-123"
    assert order.broker_order_id == "abc-123"
    assert order.status == OrderStatus.FILLED
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET
    assert order.filled_quantity == 10
    assert order.filled_price == 150.25
    assert order.submitted_at is not None

    # The submitted payload carried the expected order fields.
    payload = session.calls[0]["json"]
    assert payload["symbol"] == "AAPL"
    assert payload["qty"] == "10"
    assert payload["side"] == "buy"
    assert payload["type"] == "market"
    assert payload["time_in_force"] == "day"


def test_get_account_info_parses_fields() -> None:
    account_response = {
        "id": "acct-9",
        "cash": "5000.50",
        "buying_power": "10000.00",
        "portfolio_value": "15000.00",
        "unrealized_pl": "250.00",
        "realized_pl": "100.00",
        "currency": "USD",
    }
    broker, _ = _make_broker({("GET", "/v2/account"): account_response})

    info = broker.get_account_info()
    assert info.account_id == "acct-9"
    assert info.cash_balance == 5000.50
    assert info.buying_power == 10000.00
    assert info.portfolio_value == 15000.00
    assert info.is_paper is True


def test_get_quote_uses_data_host_and_parses_bid_ask() -> None:
    quote_response = {"quote": {"bp": 149.9, "ap": 150.1, "t": "2026-09-14T10:00:00Z"}}
    broker, session = _make_broker(
        {("GET", "/v2/stocks/AAPL/quotes/latest"): quote_response}
    )

    quote = broker.get_quote("AAPL")
    assert quote.symbol == "AAPL"
    assert quote.bid == 149.9
    assert quote.ask == 150.1
    assert session.calls[0]["url"].startswith("https://data.alpaca.markets")


# --------------------------------------------------------------------------- #
# Crypto routing
# --------------------------------------------------------------------------- #


def test_crypto_buy_posts_slash_symbol_gtc_and_fractional_qty() -> None:
    order_response = {
        "id": "crypto-1",
        "symbol": "BTC/USD",
        "side": "buy",
        "qty": "0.05",
        "type": "market",
        "time_in_force": "gtc",
        "status": "filled",
        "filled_qty": "0.05",
        "filled_avg_price": "60000.0",
    }
    broker, session = _make_broker({("POST", "/v2/orders"): order_response})

    order = broker.buy("BTC-USD", 0.05, asset_class=AssetClass.CRYPTO)

    assert order.status == OrderStatus.FILLED
    payload = session.calls[0]["json"]
    assert payload["symbol"] == "BTC/USD"
    assert payload["time_in_force"] == "gtc"
    assert payload["qty"] == "0.05"
    assert payload["side"] == "buy"


def test_equity_buy_still_posts_day() -> None:
    order_response = {
        "id": "eq-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "type": "market",
        "time_in_force": "day",
        "status": "filled",
    }
    broker, session = _make_broker({("POST", "/v2/orders"): order_response})

    broker.buy("AAPL", 10)

    payload = session.calls[0]["json"]
    assert payload["symbol"] == "AAPL"
    assert payload["time_in_force"] == "day"


def test_get_quote_crypto_uses_crypto_endpoint() -> None:
    quote_response = {
        "quotes": {
            "BTC/USD": {"bp": 59990.0, "ap": 60010.0, "t": "2026-09-14T10:00:00Z"}
        }
    }
    broker, session = _make_broker(
        {("GET", "/v1beta3/crypto/us/latest/quotes"): quote_response}
    )

    quote = broker.get_quote("BTC-USD", AssetClass.CRYPTO)

    # The canonical input symbol is preserved on the returned quote.
    assert quote.symbol == "BTC-USD"
    assert quote.bid == 59990.0
    assert quote.ask == 60010.0
    assert session.calls[0]["url"].startswith("https://data.alpaca.markets")
    assert session.calls[0]["url"].endswith("/v1beta3/crypto/us/latest/quotes")
    assert session.calls[0]["params"] == {"symbols": "BTC/USD"}


def test_get_quote_crypto_falls_back_to_trades() -> None:
    broker, _session = _make_broker(
        {
            ("GET", "/v1beta3/crypto/us/latest/quotes"): {"quotes": {}},
            ("GET", "/v1beta3/crypto/us/latest/trades"): {
                "trades": {"BTC/USD": {"p": 60050.0, "t": "2026-09-14T10:00:00Z"}}
            },
        }
    )

    quote = broker.get_quote("BTC-USD", AssetClass.CRYPTO)

    assert quote.symbol == "BTC-USD"
    assert quote.last == 60050.0


def test_parse_crypto_position_maps_to_canonical() -> None:
    positions_response = [
        {
            "symbol": "BTC/USD",
            "asset_class": "crypto",
            "qty": "0.5",
            "avg_entry_price": "60000.0",
            "current_price": "61000.0",
            "market_value": "30500.0",
            "unrealized_pl": "500.0",
        }
    ]
    broker, _ = _make_broker({("GET", "/v2/positions"): positions_response})

    positions = broker.get_positions()

    assert len(positions) == 1
    assert positions[0].symbol == "BTC-USD"
    assert positions[0].quantity == 0.5


def test_parse_equity_position_symbol_unchanged() -> None:
    positions_response = [
        {
            "symbol": "AAPL",
            "asset_class": "us_equity",
            "qty": "10",
            "avg_entry_price": "150.0",
            "current_price": "155.0",
            "market_value": "1550.0",
            "unrealized_pl": "50.0",
        }
    ]
    broker, _ = _make_broker({("GET", "/v2/positions"): positions_response})

    positions = broker.get_positions()
    assert positions[0].symbol == "AAPL"


def test_get_asset_parses_tradable_equity() -> None:
    asset_response = {
        "symbol": "AAPL",
        "class": "us_equity",
        "exchange": "NASDAQ",
        "name": "Apple Inc. Common Stock",
        "status": "active",
        "tradable": True,
        "fractionable": True,
    }
    broker, session = _make_broker({("GET", "/v2/assets/AAPL"): asset_response})

    asset = broker.get_asset("AAPL")

    assert asset is not None
    assert asset.symbol == "AAPL"
    assert asset.asset_class == AssetClass.EQUITY
    assert asset.tradable is True
    assert asset.fractionable is True
    assert asset.exchange == "NASDAQ"
    assert session.calls[0]["url"].endswith("/v2/assets/AAPL")


def test_get_asset_crypto_url_encodes_slash_symbol() -> None:
    asset_response = {
        "symbol": "BTC/USD",
        "class": "crypto",
        "status": "active",
        "tradable": True,
        "fractionable": True,
    }
    # to_alpaca_symbol turns BTC-USD into BTC/USD; the slash must be percent-encoded.
    broker, session = _make_broker(
        {("GET", "/v2/assets/BTC%2FUSD"): asset_response}
    )

    asset = broker.get_asset("BTC-USD", AssetClass.CRYPTO)

    assert asset is not None
    assert asset.symbol == "BTC/USD"
    assert asset.asset_class == AssetClass.CRYPTO
    assert asset.tradable is True
    assert session.calls[0]["url"].endswith("/v2/assets/BTC%2FUSD")


def test_get_asset_inactive_asset_is_not_tradable() -> None:
    asset_response = {
        "symbol": "OLDCO",
        "class": "us_equity",
        "status": "inactive",
        "tradable": True,
        "fractionable": False,
    }
    broker, _ = _make_broker({("GET", "/v2/assets/OLDCO"): asset_response})

    asset = broker.get_asset("OLDCO")

    assert asset is not None
    assert asset.tradable is False


def test_get_asset_missing_returns_none() -> None:
    import requests

    class NotFoundResponse:
        text = "{}"

        def raise_for_status(self) -> None:
            raise requests.exceptions.HTTPError("404 Not Found")

        def json(self) -> Any:
            return {}

    class NotFoundSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def request(self, method: str, url: str, **kwargs: Any) -> NotFoundResponse:
            self.calls.append({"method": method, "url": url, **kwargs})
            return NotFoundResponse()

    session = NotFoundSession()
    broker = AlpacaBroker(
        api_key="k", secret_key="s", paper=True, session=session
    )

    assert broker.get_asset("GHOST") is None
