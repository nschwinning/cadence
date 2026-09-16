"""Data models for broker interactions.

Ported from the trading-bot broker package: plain dataclasses and string enums
that describe orders, positions, account state, and price quotes. These carry no
persistence concerns (no ORM, no database) — they are the in-memory vocabulary
shared by the :class:`~cadence.broker.base.Broker` protocol and its
implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AssetClass(str, Enum):
    """The tradable asset class of an order/quote.

    Derived from the asset universe's ``Asset.category`` at the domain boundary
    and threaded into the broker so it can route symbols, time-in-force, and
    quote endpoints correctly. Business logic never sniffs symbol format — it
    passes this class explicitly.
    """

    EQUITY = "equity"
    CRYPTO = "crypto"


class OrderSide(str, Enum):
    """Direction of an order."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Execution type of an order."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    """Lifecycle status of an order (broker-agnostic)."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TimeInForce(str, Enum):
    """How long an order remains active."""

    DAY = "day"
    GTC = "gtc"  # Good til cancelled
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill


@dataclass(frozen=True)
class BrokerAsset:
    """A brokerage's view of a tradable instrument.

    Returned by :meth:`~cadence.broker.base.Broker.get_asset` when the broker
    lists the instrument. ``symbol`` is the broker's canonical symbol (Alpaca
    form, e.g. ``BRK.B`` / ``BTC/USD``) — the assets domain stores it so trading
    no longer has to reconstruct it. ``tradable`` reflects whether orders can be
    routed right now; ``fractionable`` whether fractional quantities are allowed.
    """

    symbol: str
    asset_class: AssetClass
    tradable: bool
    fractionable: bool = False
    exchange: str | None = None
    name: str | None = None


@dataclass
class Order:
    """Represents a trading order and its fill state."""

    symbol: str
    side: OrderSide
    quantity: float
    asset_class: AssetClass = AssetClass.EQUITY
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    order_id: str | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: float | None = None
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    broker_order_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """Whether the order has reached a terminal state."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        )


@dataclass
class Position:
    """Represents a position in a security."""

    symbol: str
    quantity: float
    avg_cost: float
    current_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float = 0.0

    @property
    def cost_basis(self) -> float:
        """Total cost of the position at its average entry price."""
        return self.quantity * self.avg_cost

    def update_market_value(self, price: float) -> None:
        """Recompute market value and unrealized P&L at ``price``."""
        self.current_price = price
        self.market_value = self.quantity * price
        self.unrealized_pnl = self.market_value - self.cost_basis


@dataclass
class AccountInfo:
    """Represents broker account information."""

    account_id: str
    cash_balance: float
    buying_power: float
    portfolio_value: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    margin_used: float = 0.0
    margin_available: float = 0.0
    currency: str = "USD"
    is_paper: bool = False


@dataclass
class Trade:
    """Represents an executed trade (fill)."""

    trade_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    executed_at: datetime
    order_id: str | None = None

    @property
    def notional(self) -> float:
        """Gross value of the trade before commission."""
        return self.quantity * self.price


@dataclass
class Quote:
    """Represents a price quote for a symbol."""

    symbol: str
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: int | None = None
    timestamp: datetime | None = None

    @property
    def mid(self) -> float | None:
        """Midpoint of bid/ask, falling back to the last trade price."""
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return self.last
