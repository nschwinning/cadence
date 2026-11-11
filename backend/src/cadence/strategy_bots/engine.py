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

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from cadence.broker.base import Broker
from cadence.broker.models import Order, OrderSide, OrderStatus
from cadence.orders import journal
from cadence.orders.gateway import OrderGateway, WouldShortError
from cadence.orders.models import OrderOwnerKind
from cadence.strategy_bots.models import BotPosition, BotSession, BotTrade

_logger = logging.getLogger(__name__)

# A fill within this of the position's quantity closes it.
_QTY_EPSILON = 1e-6

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


def book_entry_fill(
    db: Session,
    bot: BotSession,
    *,
    asset_id: int,
    ticker: str,
    symbol: str,
    quantity: float,
    price: float,
    order: Order,
    now: datetime,
    reason: str,
) -> BotTrade:
    """Book a filled entry: record the trade, open (or grow) the position, debit cash.

    A second fill for a ticker the bot already holds (only possible when an earlier fill
    is booked late by reconciliation) grows that position at the weighted-average price
    instead of opening a duplicate.
    """
    trade = _record_trade(db, bot, symbol, OrderSide.BUY, quantity, price, order, reason)
    existing = next((p for p in bot.positions if p.ticker == ticker), None)
    if existing is None:
        db.add(
            BotPosition(
                session=bot,
                asset_id=asset_id,
                ticker=ticker,
                alpaca_symbol=symbol,
                quantity=quantity,
                avg_price=price,
                opened_at=now,
            )
        )
    else:
        _logger.warning(
            "bot %s: booking a further %s %s into an open position", bot.id, quantity, ticker
        )
        total = existing.quantity + quantity
        existing.avg_price = (
            existing.quantity * existing.avg_price + quantity * price
        ) / total
        existing.quantity = total
    bot.cash -= quantity * price + trade.fees
    return trade


def book_exit_fill(
    db: Session,
    bot: BotSession,
    *,
    ticker: str,
    symbol: str,
    quantity: float,
    price: float,
    order: Order,
    reason: str,
) -> BotTrade:
    """Book a filled exit: record the trade, realise P&L, credit cash, close the position.

    The position is removed when the fill covers it and reduced otherwise. A fill for a
    position that no longer exists (only reachable through late reconciliation) still
    records the trade and the cash, without realised P&L.
    """
    trade = _record_trade(db, bot, symbol, OrderSide.SELL, quantity, price, order, reason)
    position = next((p for p in bot.positions if p.ticker == ticker), None)
    if position is None:
        _logger.warning(
            "bot %s: booking a sell of %s %s with no open position", bot.id, quantity, ticker
        )
    else:
        bot.realised_pnl += (price - position.avg_price) * quantity
        if quantity + _QTY_EPSILON >= position.quantity:
            bot.positions.remove(position)
        else:
            position.quantity -= quantity
    bot.cash += quantity * price - trade.fees
    return trade


def _record_trade(
    db: Session,
    bot: BotSession,
    symbol: str,
    side: OrderSide,
    quantity: float,
    price: float,
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
        filled_price=price,
        fees=fees,
        reason=reason,
        order_id=order.order_id,
        status=order.status.value,
    )
    db.add(trade)
    bot.total_trades += 1
    bot.total_fees += fees
    return trade


class ExecutionEngine:
    """Submits and records bot trades and maintains cash + the positions collection.

    Every order goes through a journaled :class:`~cadence.orders.gateway.OrderGateway`
    owned by the bot; the fill is booked and the journal row marked booked in the same
    unit of work. An order that has not filled when polling gives up stays journaled and
    is booked later by reconciliation; a symbol with such an unresolved order is not
    traded again until it is resolved.
    """

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

    def _gateway(self, bot: BotSession) -> OrderGateway:
        return OrderGateway(self._broker, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id)

    def _blocked(self, bot: BotSession, ticker: str) -> bool:
        if journal.has_unresolved(
            self._db, owner_kind=OrderOwnerKind.BOT, owner_id=bot.id, ticker=ticker
        ):
            _logger.info("bot %s: %s has an unresolved order; not trading it", bot.id, ticker)
            return True
        return False

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
        if shares < 1 or self._blocked(bot, ticker):
            return EngineOutcome(action="noop")

        order = self._submit_and_poll(
            self._gateway(bot).buy(
                ticker,
                float(shares),
                purpose=reason,
                broker_symbol=symbol,
                context={"asset_id": asset_id},
            )
        )
        if order.status is not OrderStatus.FILLED or order.filled_price is None:
            return EngineOutcome(action="noop")

        trade = book_entry_fill(
            self._db,
            bot,
            asset_id=asset_id,
            ticker=ticker,
            symbol=symbol,
            quantity=order.filled_quantity or float(shares),
            price=order.filled_price,
            order=order,
            now=now,
            reason=reason,
        )
        journal.mark_booked(self._db, order.client_order_id or "")
        return EngineOutcome(action="enter", trade=trade)

    def exit(
        self,
        bot: BotSession,
        position: BotPosition,
        *,
        now: datetime,
        reason: str,
    ) -> EngineOutcome:
        """Sell the entire position, record the fill, realise P&L, and credit cash.

        A sell the account cannot cover (it holds fewer shares) is refused by the gateway:
        nothing is sent, the position is left as is, and the refusal is logged.
        """
        quantity = position.quantity
        if quantity <= 0:
            bot.positions.remove(position)
            return EngineOutcome(action="noop")
        if self._blocked(bot, position.ticker):
            return EngineOutcome(action="noop")

        try:
            submitted = self._gateway(bot).sell(
                position.ticker,
                quantity,
                purpose=reason,
                broker_symbol=position.alpaca_symbol,
                context={"asset_id": position.asset_id},
            )
        except WouldShortError:
            _logger.warning(
                "bot %s: not selling %s %s — the account holds less",
                bot.id,
                quantity,
                position.ticker,
            )
            return EngineOutcome(action="noop")
        order = self._submit_and_poll(submitted)
        if order.status is not OrderStatus.FILLED or order.filled_price is None:
            return EngineOutcome(action="noop")

        trade = book_exit_fill(
            self._db,
            bot,
            ticker=position.ticker,
            symbol=position.alpaca_symbol,
            quantity=order.filled_quantity or quantity,
            price=order.filled_price,
            order=order,
            reason=reason,
        )
        journal.mark_booked(self._db, order.client_order_id or "")
        return EngineOutcome(action="exit", trade=trade)

    def _submit_and_poll(self, order: Order) -> Order:
        """Poll ``order`` until it reaches a terminal state (bounded)."""
        attempts = 0
        while not order.is_complete and attempts < self._poll_attempts:
            time.sleep(self._poll_interval)
            if order.order_id is not None:
                refreshed = self._broker.get_order(order.order_id)
                if refreshed is not None:
                    refreshed.client_order_id = order.client_order_id
                    order = refreshed
            attempts += 1
        return order
