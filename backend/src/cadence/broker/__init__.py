"""Brokerage abstraction.

The rest of the app depends only on the :class:`Broker` protocol; concrete
network access lives in :class:`AlpacaBroker`, and :class:`StubBroker` provides a
deterministic offline implementation. :func:`get_broker` selects between them
from :data:`cadence.config.settings`, mirroring how the assets/recommendations
domains choose a real provider vs. an injectable stub.
"""

from __future__ import annotations

from cadence.broker.alpaca import AlpacaBroker
from cadence.broker.base import (
    Broker,
    BrokerError,
    ConnectionError,
    OrderError,
)
from cadence.broker.models import (
    AccountInfo,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    TimeInForce,
    Trade,
)
from cadence.broker.stub import StubBroker
from cadence.config import settings

__all__ = [
    "AccountInfo",
    "AlpacaBroker",
    "Broker",
    "BrokerError",
    "ConnectionError",
    "Order",
    "OrderError",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "Quote",
    "StubBroker",
    "TimeInForce",
    "Trade",
    "get_broker",
]


def get_broker() -> Broker:
    """Provide the broker. Overridden with a fake in tests.

    Returns the offline :class:`StubBroker` when ``ALPACA_STUB`` is set (used by
    the Docker smoke / local dev); otherwise the real :class:`AlpacaBroker`,
    which reads its credentials from :data:`settings`.
    """
    if settings.ALPACA_STUB:
        return StubBroker()
    return AlpacaBroker()
