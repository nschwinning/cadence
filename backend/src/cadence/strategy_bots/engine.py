"""Risk / execution engine — order execution and value accounting.

Given sized entries and exit decisions from the tick runner, this layer submits and
polls orders through the :class:`Broker` protocol, records trades, and maintains the
session's shared ``cash`` pool and its ``positions`` collection. It is long-only and
holds at most one position per symbol (no pyramiding, no shorting). The *orchestration*
— exits before entries, deterministic ordering, the drawdown kill-switch, and
budget-bounded sizing — lives in the tick runner (:mod:`.service`); this layer provides
the primitives it drives plus the pure value helpers.

Capital accounting (shared pool across the basket):

    cash           starts at initial_capital; -= cost on a buy, += proceeds on a sell
    unrealised_pnl = Σ qty * (mark - avg_price)   over open positions
    total_value    = cash + Σ qty * mark          over open positions
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from cadence.broker.base import Broker
from cadence.broker.models import AssetClass, Order, OrderSide, OrderStatus
from cadence.strategy_bots.models import BotPosition, BotSession, BotTrade

#: Reasons recorded on the trade ledger for an engine-initiated exit.
REASON_TAKE_PROFIT = "take_profit"
REASON_STOP_LOSS = "stop_loss"
REASON_DRAWDOWN = "drawdown_kill_switch"
#: Trade reason for sells that flatten a session after it was stopped.
REASON_SESSION_STOPPED = "session_stopped"


def _mark(position: BotPosition, marks: Mapping[str, float]) -> float:
    """Mark price for ``position`` — its fresh price this tick, else its avg cost."""
    return marks.get(position.ticker, position.avg_price)


def unrealised_pnl(bot: BotSession, marks: Mapping[str, float]) -> float:
    """Mark-to-market profit/loss summed across all open positions."""
    return sum(
        position.quantity * (_mark(position, marks) - position.avg_price)
        for position in bot.positions
    )


def total_value(bot: BotSession, marks: Mapping[str, float]) -> float:
    """Total session value: shared cash plus all marked-to-market positions."""
    return bot.cash + sum(
        position.quantity * _mark(position, marks) for position in bot.positions
    )


def take_profit_stop_loss_reason(
    *,
    avg_price: float,
    price: float,
    take_profit_pct: float | None,
    stop_loss_pct: float | None,
) -> str | None:
    """Return the TP/SL exit reason if a threshold is hit for a position, else ``None``."""
    if take_profit_pct is not None and price >= avg_price * (1.0 + take_profit_pct):
        return REASON_TAKE_PROFIT
    if stop_loss_pct is not None and price <= avg_price * (1.0 - stop_loss_pct):
        return REASON_STOP_LOSS
    return None


@dataclass(frozen=True)
class EngineOutcome:
    """What the engine did for one order (an enter or an exit)."""

    #: One of "enter", "exit", or "noop".
    action: str
    #: The trade recorded, if any.
    trade: BotTrade | None = None


class ExecutionEngine:
    """Submits and records bot trades and maintains cash + the positions collection."""

    def __init__(
        self,
        db: Session,
        broker: Broker,
        *,
        poll_attempts: int = 10,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self._db = db
        self._broker = broker
        self._poll_attempts = poll_attempts
        self._poll_interval = poll_interval_seconds

    def enter(
        self,
        bot: BotSession,
        *,
        asset_id: int,
        ticker: str,
        symbol: str,
        shares: int,
        price: float,
        now: datetime,
        reason: str,
    ) -> EngineOutcome:
        """Submit a whole-share long entry; on fill create the position and debit cash."""
        if shares < 1:
            return EngineOutcome(action="noop")

        order = self._submit_and_poll(
            self._broker.buy(
                symbol=symbol,
                quantity=float(shares),
                asset_class=AssetClass.EQUITY,
            )
        )
        if order.status is not OrderStatus.FILLED or order.filled_price is None:
            return EngineOutcome(action="noop")

        filled_qty = order.filled_quantity or float(shares)
        trade = self._record_trade(bot, symbol, OrderSide.BUY, filled_qty, order, reason)
        position = BotPosition(
            session=bot,
            asset_id=asset_id,
            ticker=ticker,
            alpaca_symbol=symbol,
            quantity=filled_qty,
            avg_price=order.filled_price,
            opened_at=now,
        )
        self._db.add(position)
        bot.cash -= filled_qty * order.filled_price + trade.fees
        return EngineOutcome(action="enter", trade=trade)

    def exit(
        self,
        bot: BotSession,
        position: BotPosition,
        *,
        now: datetime,
        reason: str,
    ) -> EngineOutcome:
        """Sell the entire position, record the fill, realise P&L, and credit cash."""
        quantity = position.quantity
        if quantity <= 0:
            bot.positions.remove(position)
            return EngineOutcome(action="noop")

        order = self._submit_and_poll(
            self._broker.sell(
                symbol=position.alpaca_symbol,
                quantity=quantity,
                asset_class=AssetClass.EQUITY,
            )
        )
        if order.status is not OrderStatus.FILLED or order.filled_price is None:
            return EngineOutcome(action="noop")

        filled_qty = order.filled_quantity or quantity
        trade = self._record_trade(
            bot, position.alpaca_symbol, OrderSide.SELL, filled_qty, order, reason
        )
        bot.realised_pnl += (order.filled_price - position.avg_price) * filled_qty
        bot.cash += filled_qty * order.filled_price - trade.fees
        bot.positions.remove(position)
        return EngineOutcome(action="exit", trade=trade)

    def _record_trade(
        self,
        bot: BotSession,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order: Order,
        reason: str,
    ) -> BotTrade:
        """Persist a ``BotTrade`` row and bump the session's running totals."""
        # Alpaca equities are commission-free on paper; fees stay 0 in v1 but the
        # column is maintained so a future fee model needs no schema change.
        fees = 0.0
        trade = BotTrade(
            session=bot,
            side=side.value,
            ticker=symbol,
            quantity=quantity,
            filled_price=order.filled_price,
            fees=fees,
            reason=reason,
            order_id=order.order_id,
            status=order.status.value,
        )
        self._db.add(trade)
        bot.total_trades += 1
        bot.total_fees += fees
        return trade

    def _submit_and_poll(self, order: Order) -> Order:
        """Poll ``order`` until it reaches a terminal state (bounded)."""
        attempts = 0
        while not order.is_complete and attempts < self._poll_attempts:
            time.sleep(self._poll_interval)
            if order.order_id is not None:
                refreshed = self._broker.get_order(order.order_id)
                if refreshed is not None:
                    order = refreshed
            attempts += 1
        return order
