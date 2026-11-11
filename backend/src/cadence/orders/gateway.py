"""The single path through which Cadence submits broker orders.

:class:`OrderGateway` wraps a :class:`~cadence.broker.base.Broker` for one owner. Each
``buy``/``sell``:

1. for a sell, refuses — sending nothing — when the account holds less than the
   quantity (long-only guard, :class:`WouldShortError`);
2. durably records the intended order with a fresh client order id;
3. submits it with that client order id (the broker refuses a duplicate);
4. records the broker's answer, or the error, and returns the order.

The owner books a fill into its ledger and calls :func:`cadence.orders.journal.mark_booked`
in the same unit of work; anything it never books is picked up by reconciliation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from cadence.broker.base import Broker, BrokerError
from cadence.broker.models import AssetClass, Order, OrderSide
from cadence.broker.symbols import symbol_key
from cadence.orders import journal
from cadence.orders.models import JournalState, OrderOwnerKind

_logger = logging.getLogger(__name__)

#: Quantities are floats; a holding within this of the sell quantity is enough.
QUANTITY_EPSILON = 1e-6

#: How long an owner keeps reconciliation away from an order it just sent.
BOT_LEASE = timedelta(minutes=2)
AI_SESSION_LEASE = timedelta(minutes=30)
ADMIN_LEASE = timedelta(minutes=1)

_DEFAULT_LEASES = {
    OrderOwnerKind.BOT: BOT_LEASE,
    OrderOwnerKind.AI_SESSION: AI_SESSION_LEASE,
    OrderOwnerKind.ADMIN: ADMIN_LEASE,
}


class WouldShortError(BrokerError):
    """A sell was refused because the account holds less than its quantity."""


class OrderGateway:
    """Journaled, long-only order submission for one owner."""

    def __init__(
        self,
        broker: Broker,
        *,
        owner_kind: OrderOwnerKind,
        owner_id: uuid.UUID | None = None,
        lease: timedelta | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.broker = broker
        self.owner_kind = owner_kind
        self.owner_id = owner_id
        self._lease = lease or _DEFAULT_LEASES[owner_kind]
        self._context = context or {}

    def buy(
        self,
        ticker: str,
        quantity: float,
        *,
        purpose: str,
        asset_class: AssetClass = AssetClass.EQUITY,
        broker_symbol: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Order:
        """Submit a journaled market buy."""
        return self._submit(
            OrderSide.BUY, ticker, quantity, purpose, asset_class, broker_symbol, context
        )

    def sell(
        self,
        ticker: str,
        quantity: float,
        *,
        purpose: str,
        asset_class: AssetClass = AssetClass.EQUITY,
        broker_symbol: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Order:
        """Submit a journaled market sell, refused if the account holds less."""
        return self._submit(
            OrderSide.SELL, ticker, quantity, purpose, asset_class, broker_symbol, context
        )

    # ------------------------------------------------------------------
    def held_quantity(self, symbol: str) -> float:
        """The account's total holding of ``symbol`` (any spelling)."""
        key = symbol_key(symbol)
        return sum(
            p.quantity for p in self.broker.get_positions() if symbol_key(p.symbol) == key
        )

    def _submit(
        self,
        side: OrderSide,
        ticker: str,
        quantity: float,
        purpose: str,
        asset_class: AssetClass,
        broker_symbol: str | None,
        context: dict[str, Any] | None,
    ) -> Order:
        symbol = broker_symbol or ticker
        record: dict[str, Any] = {
            "owner_kind": self.owner_kind,
            "owner_id": self.owner_id,
            "ticker": ticker,
            "broker_symbol": symbol,
            "asset_class": asset_class.value,
            "side": side.value,
            "quantity": quantity,
            "purpose": purpose,
            "context": {**self._context, **(context or {})},
            "lease": self._lease,
        }

        if side is OrderSide.SELL:
            held = self.held_quantity(symbol)
            if held + QUANTITY_EPSILON < quantity:
                message = (
                    f"Refused: selling {quantity:g} {symbol} would exceed the "
                    f"{max(held, 0.0):g} the account holds"
                )
                journal.record_intent(**record, state=JournalState.REFUSED, error=message)
                _logger.warning("order gateway: %s (%s)", message, purpose)
                raise WouldShortError(message)

        client_order_id = journal.record_intent(**record)
        place = self.broker.sell if side is OrderSide.SELL else self.broker.buy
        try:
            order = place(
                symbol, quantity, asset_class=asset_class, client_order_id=client_order_id
            )
        except Exception as exc:
            journal.record_submitted(client_order_id, order=None, error=str(exc) or repr(exc))
            raise
        order.client_order_id = client_order_id
        journal.record_submitted(
            client_order_id, order=order, resolved=self.owner_kind is OrderOwnerKind.ADMIN
        )
        return order
