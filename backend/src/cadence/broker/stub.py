"""Deterministic in-memory broker for offline runs and tests.

:class:`StubBroker` simulates a brokerage with no network access and no
randomness: quotes are a stable function of the symbol, market orders fill
immediately at the quote price, and fills update cash and positions. It satisfies
the :class:`~cadence.broker.base.Broker` protocol, so the executor / rebalancer
can drive it exactly like the real Alpaca client. Selected by
:func:`~cadence.broker.get_broker` when ``ALPACA_STUB`` is set.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cadence.broker.base import OrderError
from cadence.broker.models import (
    AccountInfo,
    AssetClass,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    TimeInForce,
)

DEFAULT_CASH = 100_000.0


def _deterministic_price(symbol: str) -> float:
    """Return a stable, positive price derived only from ``symbol``.

    No randomness or wall-clock is used, so the same symbol always yields the
    same price across processes and runs — letting tests assert exact cash and
    position math.
    """
    seed = sum(ord(char) for char in symbol.upper())
    # Map into a plausible equity range (~$50–$550) with cents that vary by
    # symbol length, keeping every price strictly positive.
    return round(50.0 + (seed % 500) + (len(symbol) % 100) / 100.0, 2)


class StubBroker:
    """In-memory :class:`Broker` implementation with deterministic behavior."""

    def __init__(self, initial_cash: float = DEFAULT_CASH) -> None:
        self._initial_cash = initial_cash
        self._cash = initial_cash
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._realized_pnl = 0.0
        self._order_seq = 0

    # Account / positions -------------------------------------------------
    def get_account_info(self) -> AccountInfo:
        """Return simulated account state, marking positions to market."""
        portfolio_value = self._cash
        unrealized_pnl = 0.0
        for pos in self._positions.values():
            if pos.quantity == 0:
                continue
            pos.update_market_value(_deterministic_price(pos.symbol))
            portfolio_value += pos.market_value or 0.0
            unrealized_pnl += pos.unrealized_pnl or 0.0

        return AccountInfo(
            account_id="STUB",
            cash_balance=self._cash,
            buying_power=self._cash,
            portfolio_value=portfolio_value,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=self._realized_pnl,
            is_paper=True,
        )

    def get_positions(self) -> list[Position]:
        """Return all non-empty positions marked to market."""
        positions = []
        for pos in self._positions.values():
            if pos.quantity != 0:
                pos.update_market_value(_deterministic_price(pos.symbol))
                positions.append(pos)
        return positions

    def get_position(self, symbol: str) -> Position | None:
        """Return the position for ``symbol`` or ``None`` if flat."""
        pos = self._positions.get(symbol)
        if pos and pos.quantity != 0:
            pos.update_market_value(_deterministic_price(symbol))
            return pos
        return None

    # Market data ---------------------------------------------------------
    def get_quote(
        self, symbol: str, asset_class: AssetClass = AssetClass.EQUITY
    ) -> Quote:
        """Return a deterministic quote for ``symbol`` (``asset_class`` ignored)."""
        price = _deterministic_price(symbol)
        return Quote(
            symbol=symbol,
            bid=round(price - 0.01, 2),
            ask=round(price + 0.01, 2),
            last=price,
            volume=1_000_000,
            timestamp=datetime.now(UTC),
        )

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Return deterministic quotes for several symbols."""
        return {symbol: self.get_quote(symbol) for symbol in symbols}

    # Orders --------------------------------------------------------------
    def submit_order(self, order: Order) -> Order:
        """Fill a market order immediately; store limit orders as open."""
        price = _deterministic_price(order.symbol)

        if order.order_type == OrderType.MARKET:
            return self._execute(order, price)

        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise OrderError("Limit price required for limit orders")
            can_fill = (
                order.side == OrderSide.BUY and price <= order.limit_price
            ) or (order.side == OrderSide.SELL and price >= order.limit_price)
            if can_fill:
                return self._execute(order, order.limit_price)
            order.order_id = self._next_order_id()
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now(UTC)
            self._orders[order.order_id] = order
            return order

        raise OrderError(
            f"Order type {order.order_type} not supported by the stub broker"
        )

    def _execute(self, order: Order, fill_price: float) -> Order:
        """Fill ``order`` at ``fill_price``, updating cash and positions."""
        if order.side == OrderSide.BUY:
            cost = order.quantity * fill_price
            if cost > self._cash:
                raise OrderError(
                    f"Insufficient buying power. Need {cost:,.2f}, "
                    f"have {self._cash:,.2f}"
                )
            self._cash -= cost
        else:
            pos = self._positions.get(order.symbol)
            if pos is None or pos.quantity < order.quantity:
                held = pos.quantity if pos else 0
                raise OrderError(
                    f"Insufficient shares to sell. Have {held}, "
                    f"need {order.quantity}"
                )
            self._cash += order.quantity * fill_price
            self._realized_pnl += (fill_price - pos.avg_cost) * order.quantity

        now = datetime.now(UTC)
        order.order_id = self._next_order_id()
        order.broker_order_id = order.order_id
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.filled_price = fill_price
        order.submitted_at = now
        order.filled_at = now
        self._orders[order.order_id] = order

        self._apply_to_position(order.symbol, order.side, order.quantity, fill_price)
        return order

    def _apply_to_position(
        self, symbol: str, side: OrderSide, quantity: float, price: float
    ) -> None:
        pos = self._positions.get(symbol)
        if pos is None:
            pos = Position(symbol=symbol, quantity=0.0, avg_cost=0.0)
            self._positions[symbol] = pos

        if side == OrderSide.BUY:
            total_cost = pos.quantity * pos.avg_cost + quantity * price
            pos.quantity += quantity
            pos.avg_cost = total_cost / pos.quantity if pos.quantity > 0 else 0.0
        else:
            pos.quantity -= quantity
            if pos.quantity <= 0:
                pos.quantity = 0.0
                pos.avg_cost = 0.0

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open (unfilled) order; return ``True`` on success."""
        order = self._orders.get(order_id)
        if order and order.status == OrderStatus.SUBMITTED:
            order.status = OrderStatus.CANCELLED
            return True
        return False

    def get_order(self, order_id: str) -> Order | None:
        """Return the order with ``order_id`` or ``None``."""
        return self._orders.get(order_id)

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """Return unfilled orders, optionally filtered by symbol."""
        orders = [
            o for o in self._orders.values() if o.status == OrderStatus.SUBMITTED
        ]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    # Convenience helpers -------------------------------------------------
    def buy(
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        asset_class: AssetClass = AssetClass.EQUITY,
    ) -> Order:
        """Submit a buy order (``asset_class`` accepted for parity, unused)."""
        return self.submit_order(
            Order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                asset_class=asset_class,
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
        asset_class: AssetClass = AssetClass.EQUITY,
    ) -> Order:
        """Submit a sell order (``asset_class`` accepted for parity, unused)."""
        return self.submit_order(
            Order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                asset_class=asset_class,
                order_type=order_type,
                limit_price=limit_price,
                time_in_force=time_in_force,
            )
        )

    # Market status -------------------------------------------------------
    def is_market_open(self) -> bool:
        """The stub market is always open."""
        return True

    # Test/helper utilities ----------------------------------------------
    def _next_order_id(self) -> str:
        self._order_seq += 1
        return f"stub-{self._order_seq:06d}"

    def reset(self) -> None:
        """Restore the stub to its initial cash-only state."""
        self._cash = self._initial_cash
        self._positions.clear()
        self._orders.clear()
        self._realized_pnl = 0.0
        self._order_seq = 0
