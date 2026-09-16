"""Broker protocol and domain exceptions.

External brokerage I/O lives behind the :class:`Broker` protocol so the rest of
the domain (the executor / rebalancer) depends only on this interface — never on
Alpaca or ``requests`` directly. A real :class:`~cadence.broker.alpaca.AlpacaBroker`
and an injectable :class:`~cadence.broker.stub.StubBroker` both satisfy it, and
:func:`get_broker` selects between them from configuration. This mirrors how the
assets domain hides market-data access behind ``MarketDataProvider``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cadence.broker.models import (
    AccountInfo,
    AssetClass,
    BrokerAsset,
    Order,
    OrderType,
    Position,
    Quote,
    TimeInForce,
)


class BrokerError(Exception):
    """Base exception for broker errors."""


class ConnectionError(BrokerError):
    """Raised when the broker connection or configuration fails.

    Shadows the builtin ``ConnectionError`` within the broker domain on purpose,
    matching trading-bot's naming so ported code reads identically. Callers that
    need the builtin should import it explicitly.
    """


class OrderError(BrokerError):
    """Raised when order submission or management fails."""


@runtime_checkable
class Broker(Protocol):
    """Interface for placing and tracking trades against a brokerage.

    Captures exactly the operations the executor / rebalancer need. Because it is
    ``runtime_checkable``, ``isinstance(obj, Broker)`` verifies method presence,
    which the stub relies on in tests.
    """

    # Account / positions
    def get_account_info(self) -> AccountInfo:
        """Return account balances and buying power."""
        ...

    def get_positions(self) -> list[Position]:
        """Return all currently held positions."""
        ...

    def get_position(self, symbol: str) -> Position | None:
        """Return the position for ``symbol`` or ``None`` if flat."""
        ...

    # Asset reference data
    def get_asset(
        self, symbol: str, asset_class: AssetClass = ...
    ) -> BrokerAsset | None:
        """Look up a tradable instrument by canonical ``symbol``.

        Returns the broker's :class:`BrokerAsset` (including its canonical symbol
        and tradability), or ``None`` if the broker does not list ``symbol``.
        """
        ...

    # Market data
    def get_quote(
        self, symbol: str, asset_class: AssetClass = ...
    ) -> Quote:
        """Return the latest quote for ``symbol``."""
        ...

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Return quotes for several symbols keyed by symbol."""
        ...

    # Orders
    def submit_order(self, order: Order) -> Order:
        """Submit ``order`` and return it updated with broker id/status."""
        ...

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order; return ``True`` on success."""
        ...

    def get_order(self, order_id: str) -> Order | None:
        """Return the order with ``order_id`` or ``None`` if unknown."""
        ...

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """Return open orders, optionally filtered by ``symbol``."""
        ...

    # Convenience helpers
    def buy(
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = ...,
        limit_price: float | None = ...,
        time_in_force: TimeInForce = ...,
        asset_class: AssetClass = ...,
    ) -> Order:
        """Submit a buy order and return the resulting :class:`Order`."""
        ...

    def sell(
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = ...,
        limit_price: float | None = ...,
        time_in_force: TimeInForce = ...,
        asset_class: AssetClass = ...,
    ) -> Order:
        """Submit a sell order and return the resulting :class:`Order`."""
        ...

    # Market status
    def is_market_open(self) -> bool:
        """Return whether the market is currently open for trading."""
        ...
