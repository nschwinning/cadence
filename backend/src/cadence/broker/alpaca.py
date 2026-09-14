"""Alpaca brokerage client (``requests``-based).

Ported from trading-bot's ``AlpacaClient`` and adapted to cadence conventions:
credentials and paper/live selection come from :data:`cadence.config.settings`
rather than ad-hoc env reads, and the client satisfies the
:class:`~cadence.broker.base.Broker` protocol directly (no explicit
connect/disconnect handshake). Trading endpoints target the paper or live API
host; quote endpoints target the Alpaca market-data host.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from typing import Any, Protocol, cast

import requests

from cadence.broker.base import BrokerError, ConnectionError, OrderError
from cadence.broker.models import (
    AccountInfo,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    TimeInForce,
)
from cadence.config import settings

logger = logging.getLogger(__name__)

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
LIVE_BASE_URL = "https://api.alpaca.markets"
DATA_BASE_URL = "https://data.alpaca.markets"


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an Alpaca ISO-8601 timestamp (``Z`` suffix supported)."""
    if not value:
        return None
    return datetime.fromisoformat(value)


class _Session(Protocol):
    """Minimal ``requests``-compatible session used for dependency injection."""

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        ...


class AlpacaBroker:
    """Alpaca REST client implementing the :class:`Broker` protocol.

    Credentials and paper/live mode default to :data:`settings`; they can be
    overridden per-instance (used by tests). A ``session`` implementing the
    ``requests`` ``request`` signature may be injected so tests never touch the
    network.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool | None = None,
        session: _Session | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.ALPACA_API_KEY
        self._secret_key = (
            secret_key if secret_key is not None else settings.ALPACA_SECRET_KEY
        )
        self._paper = paper if paper is not None else settings.ALPACA_PAPER
        self._session: _Session = session or cast("_Session", requests)

        if not self._api_key or not self._api_key.strip():
            raise ConnectionError(
                "Alpaca API credentials required: ALPACA_API_KEY is missing or blank."
            )
        if not self._secret_key or not self._secret_key.strip():
            raise ConnectionError(
                "Alpaca API credentials required: ALPACA_SECRET_KEY is missing or "
                "blank."
            )

        self._base_url = PAPER_BASE_URL if self._paper else LIVE_BASE_URL

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret_key,
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        base_url: str | None = None,
    ) -> Any:
        """Make an authenticated API request and parse the JSON body.

        Returns the decoded JSON (an object or array) or ``None`` for an empty
        body. Typed as ``Any`` because the shape is endpoint-specific; each caller
        reads the fields it expects.
        """
        url = f"{base_url or self._base_url}{endpoint}"
        try:
            response = self._session.request(
                method,
                url,
                headers=self._headers,
                params=params,
                json=json,
                timeout=30,
            )
            response.raise_for_status()
            if response.text:
                return response.json()
            return None
        except requests.exceptions.HTTPError as exc:
            error_msg = str(exc)
            with contextlib.suppress(ValueError, AttributeError, TypeError):
                error_msg = exc.response.json().get("message", str(exc))
            raise OrderError(f"Alpaca API error: {error_msg}") from exc
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"Alpaca connection error: {exc}") from exc

    # Account / positions -------------------------------------------------
    def get_account_info(self) -> AccountInfo:
        """Get account information."""
        account = self._request("GET", "/v2/account") or {}
        return AccountInfo(
            account_id=account.get("id", ""),
            cash_balance=float(account.get("cash", 0)),
            buying_power=float(account.get("buying_power", 0)),
            portfolio_value=float(account.get("portfolio_value", 0)),
            unrealized_pnl=float(account.get("unrealized_pl", 0)),
            realized_pnl=float(account.get("realized_pl", 0)),
            currency=account.get("currency", "USD"),
            is_paper=self._paper,
        )

    def get_positions(self) -> list[Position]:
        """Get all positions."""
        positions_data = self._request("GET", "/v2/positions") or []
        return [self._parse_position(pos) for pos in positions_data]

    def get_position(self, symbol: str) -> Position | None:
        """Get the position for a single symbol, or ``None`` if flat."""
        try:
            pos = self._request("GET", f"/v2/positions/{symbol}")
        except OrderError:
            return None
        if not pos:
            return None
        return self._parse_position(pos)

    # Orders --------------------------------------------------------------
    def submit_order(self, order: Order) -> Order:
        """Submit an order and update it from the broker response."""
        order_data: dict[str, str] = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": order.side.value,
            "type": self._map_order_type(order.order_type),
            "time_in_force": self._map_time_in_force(order.time_in_force),
        }

        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise OrderError("Limit price required for limit orders")
            order_data["limit_price"] = str(order.limit_price)

        if order.order_type == OrderType.STOP:
            if order.stop_price is None:
                raise OrderError("Stop price required for stop orders")
            order_data["stop_price"] = str(order.stop_price)

        if order.order_type == OrderType.STOP_LIMIT:
            if order.limit_price is None or order.stop_price is None:
                raise OrderError(
                    "Limit and stop price required for stop-limit orders"
                )
            order_data["limit_price"] = str(order.limit_price)
            order_data["stop_price"] = str(order.stop_price)

        result = self._request("POST", "/v2/orders", json=order_data) or {}

        order.order_id = result.get("id")
        order.broker_order_id = result.get("id")
        order.status = self._map_order_status(result.get("status"))
        order.submitted_at = _parse_iso(result.get("submitted_at"))
        order.filled_quantity = float(result.get("filled_qty", 0))
        order.filled_price = (
            float(result["filled_avg_price"])
            if result.get("filled_avg_price")
            else None
        )

        logger.info(
            "Submitted order: %s %s %s",
            order.side.value,
            order.quantity,
            order.symbol,
        )
        return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order; return ``True`` on success."""
        try:
            self._request("DELETE", f"/v2/orders/{order_id}")
        except OrderError:
            return False
        logger.info("Cancelled order: %s", order_id)
        return True

    def get_order(self, order_id: str) -> Order | None:
        """Get an order by id, or ``None`` if not found."""
        try:
            result = self._request("GET", f"/v2/orders/{order_id}")
        except OrderError:
            return None
        if not result:
            return None
        return self._parse_order(result)

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """Get open orders, optionally filtered by symbol."""
        params: dict[str, str] = {"status": "open"}
        if symbol:
            params["symbols"] = symbol
        results = self._request("GET", "/v2/orders", params=params) or []
        return [self._parse_order(o) for o in results]

    # Market data ---------------------------------------------------------
    def get_quote(self, symbol: str) -> Quote:
        """Get the latest quote, falling back to the latest trade price."""
        try:
            result = self._request(
                "GET",
                f"/v2/stocks/{symbol}/quotes/latest",
                base_url=DATA_BASE_URL,
            )
            quote_data = (result or {}).get("quote", {})
            return Quote(
                symbol=symbol,
                bid=float(quote_data.get("bp", 0)) or None,
                ask=float(quote_data.get("ap", 0)) or None,
                timestamp=_parse_iso(quote_data.get("t")),
            )
        except (BrokerError, ValueError, KeyError, TypeError):
            # Quote endpoint unavailable/empty: fall back to the latest trade.
            try:
                result = self._request(
                    "GET",
                    f"/v2/stocks/{symbol}/trades/latest",
                    base_url=DATA_BASE_URL,
                )
                trade_data = (result or {}).get("trade", {})
                return Quote(
                    symbol=symbol,
                    last=float(trade_data.get("p", 0)) or None,
                    volume=int(trade_data.get("s", 0)) or None,
                    timestamp=_parse_iso(trade_data.get("t")),
                )
            except (BrokerError, ValueError, KeyError, TypeError):
                return Quote(symbol=symbol)

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Get quotes for multiple symbols."""
        return {symbol: self.get_quote(symbol) for symbol in symbols}

    # Convenience helpers -------------------------------------------------
    def buy(
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> Order:
        """Submit a buy order."""
        return self.submit_order(
            Order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                time_in_force=time_in_force,
            )
        )

    def sell(
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> Order:
        """Submit a sell order."""
        return self.submit_order(
            Order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price,
                time_in_force=time_in_force,
            )
        )

    # Market status -------------------------------------------------------
    def get_clock(self) -> dict[str, Any]:
        """Get the market clock (open/close times, ``is_open``)."""
        clock = self._request("GET", "/v2/clock") or {}
        return cast("dict[str, Any]", clock)

    def is_market_open(self) -> bool:
        """Check whether the market is currently open."""
        return bool(self.get_clock().get("is_open", False))

    # Parsing helpers -----------------------------------------------------
    @staticmethod
    def _parse_position(pos: dict[str, Any]) -> Position:
        return Position(
            symbol=cast("str", pos.get("symbol")),
            quantity=float(pos.get("qty", 0)),
            avg_cost=float(pos.get("avg_entry_price", 0)),
            current_price=float(pos.get("current_price", 0)),
            market_value=float(pos.get("market_value", 0)),
            unrealized_pnl=float(pos.get("unrealized_pl", 0)),
        )

    @staticmethod
    def _map_order_type(order_type: OrderType) -> str:
        mapping = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP: "stop",
            OrderType.STOP_LIMIT: "stop_limit",
        }
        return mapping.get(order_type, "market")

    @staticmethod
    def _map_time_in_force(tif: TimeInForce) -> str:
        mapping = {
            TimeInForce.DAY: "day",
            TimeInForce.GTC: "gtc",
            TimeInForce.IOC: "ioc",
            TimeInForce.FOK: "fok",
        }
        return mapping.get(tif, "day")

    @staticmethod
    def _map_order_status(status: str | None) -> OrderStatus:
        mapping = {
            "new": OrderStatus.SUBMITTED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "done_for_day": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
            "replaced": OrderStatus.CANCELLED,
            "pending_cancel": OrderStatus.PENDING,
            "pending_replace": OrderStatus.PENDING,
            "pending_new": OrderStatus.PENDING,
            "accepted": OrderStatus.SUBMITTED,
            "rejected": OrderStatus.REJECTED,
        }
        return mapping.get(status or "", OrderStatus.PENDING)

    @classmethod
    def _parse_order(cls, data: dict[str, Any]) -> Order:
        """Parse an Alpaca order response into an :class:`Order`."""
        return Order(
            symbol=cast("str", data.get("symbol")),
            side=OrderSide.BUY if data.get("side") == "buy" else OrderSide.SELL,
            quantity=float(data.get("qty", 0)),
            order_type=cls._parse_order_type(data.get("type")),
            limit_price=(
                float(data["limit_price"]) if data.get("limit_price") else None
            ),
            stop_price=(
                float(data["stop_price"]) if data.get("stop_price") else None
            ),
            time_in_force=cls._parse_time_in_force(data.get("time_in_force")),
            order_id=data.get("id"),
            broker_order_id=data.get("id"),
            status=cls._map_order_status(data.get("status")),
            filled_quantity=float(data.get("filled_qty", 0)),
            filled_price=(
                float(data["filled_avg_price"])
                if data.get("filled_avg_price")
                else None
            ),
            submitted_at=_parse_iso(data.get("submitted_at")),
            filled_at=_parse_iso(data.get("filled_at")),
        )

    @staticmethod
    def _parse_order_type(type_str: str | None) -> OrderType:
        mapping = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop": OrderType.STOP,
            "stop_limit": OrderType.STOP_LIMIT,
        }
        return mapping.get(type_str or "", OrderType.MARKET)

    @staticmethod
    def _parse_time_in_force(tif_str: str | None) -> TimeInForce:
        mapping = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "ioc": TimeInForce.IOC,
            "fok": TimeInForce.FOK,
        }
        return mapping.get(tif_str or "", TimeInForce.DAY)
