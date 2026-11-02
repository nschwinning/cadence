"""Risk / execution engine — layer 2 of the three-layer execution model.

Shared by every strategy: given a strategy :class:`Signal`, the latest price, and a
session's live state, it sizes and submits orders through the :class:`Broker`
protocol, polls fills to a terminal state, records trades, maintains inline
position state, and enforces the risk rules that sit *above* the strategy —
optional take-profit / stop-loss and the drawdown kill-switch. It is long-only and
holds at most one all-in whole-share position per session (no pyramiding, no
shorting).

Capital accounting (v1, single position, no capital increase):

    cash            = allocated_capital + realised_pnl - total_fees - qty*avg_price
    unrealised_pnl  = qty * (price - avg_price)
    total_value     = allocated_capital + realised_pnl - total_fees + unrealised_pnl
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from math import floor

from sqlalchemy.orm import Session

from cadence.broker.base import Broker
from cadence.broker.models import AssetClass, Order, OrderSide, OrderStatus
from cadence.strategy_bots.constants import BotSessionStatus
from cadence.strategy_bots.models import BotSession, BotTrade
from cadence.strategy_bots.strategy import Signal, SignalAction

#: Reasons recorded on the trade ledger for an engine-initiated exit.
REASON_TAKE_PROFIT = "take_profit"
REASON_STOP_LOSS = "stop_loss"
REASON_DRAWDOWN = "drawdown_kill_switch"


@dataclass(frozen=True)
class EngineOutcome:
    """What the engine did on one tick for one session."""

    #: One of "enter", "exit", "hold", "drawdown_stop", or "noop".
    action: str
    #: The trade recorded this tick, if any.
    trade: BotTrade | None = None
    #: Whether the session was stopped by the drawdown kill-switch.
    stopped: bool = False


def current_cash(bot: BotSession) -> float:
    """Uninvested cash available to the session right now."""
    invested = 0.0
    if not bot.is_flat and bot.position_avg_price is not None:
        invested = (bot.position_qty or 0.0) * bot.position_avg_price
    return bot.allocated_capital + bot.realised_pnl - bot.total_fees - invested


def unrealised_pnl(bot: BotSession, price: float) -> float:
    """Mark-to-market profit/loss on the open position (0 when flat)."""
    if bot.is_flat or bot.position_avg_price is None:
        return 0.0
    return (bot.position_qty or 0.0) * (price - bot.position_avg_price)


def total_value(bot: BotSession, price: float) -> float:
    """Total session value: cash plus the marked-to-market position."""
    return (
        bot.allocated_capital
        + bot.realised_pnl
        - bot.total_fees
        + unrealised_pnl(bot, price)
    )


class ExecutionEngine:
    """Sizes, submits, and records bot trades and enforces the risk rules."""

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

    def run(
        self,
        bot: BotSession,
        signal: Signal,
        price: float,
        *,
        now: datetime,
        symbol: str | None = None,
    ) -> EngineOutcome:
        """Apply the risk rules then the strategy signal to ``bot`` at ``price``.

        Risk exits (drawdown, take-profit, stop-loss) are evaluated independently
        of — and take precedence over — the strategy signal. ``symbol`` overrides
        the broker symbol (defaults to the session's ticker).
        """
        trade_symbol = symbol or bot.ticker

        # Peak high-water mark, for the drawdown kill-switch.
        value = total_value(bot, price)
        bot.peak_value = max(bot.peak_value, value)

        # 1. Drawdown kill-switch — exit any position and stop the session. Applies
        #    whether or not a position is currently open.
        if value <= bot.peak_value * (1.0 - bot.drawdown_stop_pct):
            trade = None
            if not bot.is_flat:
                trade = self._exit(bot, trade_symbol, price, now, REASON_DRAWDOWN)
            bot.status = BotSessionStatus.STOPPED.value
            bot.last_tick_at = now
            return EngineOutcome(action="drawdown_stop", trade=trade, stopped=True)

        outcome = EngineOutcome(action="hold")
        if not bot.is_flat:
            # 2. Take-profit / stop-loss, independent of the strategy signal.
            risk_reason = self._take_profit_stop_loss_reason(bot, price)
            if risk_reason is not None:
                trade = self._exit(bot, trade_symbol, price, now, risk_reason)
                outcome = EngineOutcome(action="exit", trade=trade)
            elif signal.action is SignalAction.EXIT:
                trade = self._exit(bot, trade_symbol, price, now, signal.reason)
                outcome = EngineOutcome(action="exit", trade=trade)
        elif signal.action is SignalAction.ENTER_LONG:
            # 3. Strategy entry — only when flat (no pyramiding).
            trade = self._enter(bot, trade_symbol, price, now, signal.reason)
            outcome = EngineOutcome(
                action="enter" if trade is not None else "noop", trade=trade
            )

        bot.last_tick_at = now
        return outcome

    # Risk rules ----------------------------------------------------------
    def _take_profit_stop_loss_reason(
        self, bot: BotSession, price: float
    ) -> str | None:
        """Return the TP/SL exit reason if a threshold is hit, else ``None``."""
        avg = bot.position_avg_price
        if avg is None:
            return None
        if bot.take_profit_pct is not None and price >= avg * (
            1.0 + bot.take_profit_pct
        ):
            return REASON_TAKE_PROFIT
        if bot.stop_loss_pct is not None and price <= avg * (
            1.0 - bot.stop_loss_pct
        ):
            return REASON_STOP_LOSS
        return None

    # Order execution -----------------------------------------------------
    def _enter(
        self,
        bot: BotSession,
        symbol: str,
        price: float,
        now: datetime,
        reason: str,
    ) -> BotTrade | None:
        """Size and submit an all-in whole-share long entry; record the fill."""
        capital = current_cash(bot)
        affordable = capital * (1.0 - bot.cash_buffer_pct)
        quantity = floor(affordable / price) if price > 0 else 0
        if quantity <= 0:
            return None

        order = self._submit_and_poll(
            self._broker.buy(
                symbol=symbol,
                quantity=float(quantity),
                asset_class=AssetClass.EQUITY,
            )
        )
        if order.status is not OrderStatus.FILLED or order.filled_price is None:
            return None

        filled_qty = order.filled_quantity or float(quantity)
        trade = self._record_trade(
            bot, symbol, OrderSide.BUY, filled_qty, order, reason
        )
        bot.position_qty = filled_qty
        bot.position_avg_price = order.filled_price
        bot.position_opened_at = now
        return trade

    def _exit(
        self,
        bot: BotSession,
        symbol: str,
        price: float,
        now: datetime,
        reason: str,
    ) -> BotTrade | None:
        """Sell the entire position, record the fill, and realise the P&L."""
        quantity = bot.position_qty or 0.0
        avg = bot.position_avg_price or 0.0
        if quantity <= 0:
            return None

        order = self._submit_and_poll(
            self._broker.sell(
                symbol=symbol,
                quantity=quantity,
                asset_class=AssetClass.EQUITY,
            )
        )
        if order.status is not OrderStatus.FILLED or order.filled_price is None:
            return None

        filled_qty = order.filled_quantity or quantity
        trade = self._record_trade(
            bot, symbol, OrderSide.SELL, filled_qty, order, reason
        )
        bot.realised_pnl += (order.filled_price - avg) * filled_qty
        bot.position_qty = None
        bot.position_avg_price = None
        bot.position_opened_at = None
        return trade

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
