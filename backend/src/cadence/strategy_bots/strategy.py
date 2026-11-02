"""Pure strategy contract for the strategy-bot subsystem.

Layer 1 of the three-layer execution model. A strategy is a *pure signal
generator*: given recent bars, the current position, and validated parameters it
returns a :class:`Signal` (``ENTER_LONG`` / ``EXIT`` / ``HOLD``) plus a
human-readable reason. It performs no I/O and holds no persisted state, so it is
trivially unit-testable and shared by every bot regardless of how the bars are
sourced (the :mod:`.market_data` seam) or how orders are executed (the
:mod:`.engine` layer).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class SignalAction(StrEnum):
    """The three actions a strategy can emit on a tick."""

    ENTER_LONG = "enter_long"
    EXIT = "exit"
    HOLD = "hold"


@dataclass(frozen=True)
class Signal:
    """A strategy's decision for one tick: an action and why it was chosen."""

    action: SignalAction
    reason: str

    @classmethod
    def hold(cls, reason: str) -> Signal:
        """A HOLD signal (the default no-op decision)."""
        return cls(SignalAction.HOLD, reason)

    @classmethod
    def enter_long(cls, reason: str) -> Signal:
        """An ENTER_LONG signal."""
        return cls(SignalAction.ENTER_LONG, reason)

    @classmethod
    def exit(cls, reason: str) -> Signal:
        """An EXIT signal."""
        return cls(SignalAction.EXIT, reason)


@dataclass(frozen=True)
class Bar:
    """A single OHLCV price bar at the configured signal timeframe.

    The in-memory price primitive the strategy reasons over and the
    :mod:`.market_data` seam returns. ``timestamp`` is the bar's open time
    (timezone-aware); the strategy itself reads only ``close`` in v1.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class PositionView:
    """A read-only view of a session's open position passed to a strategy.

    ``None`` is passed instead when the session is flat; an instance with a
    positive ``quantity`` means a long position is open.
    """

    quantity: float
    avg_price: float

    @property
    def is_open(self) -> bool:
        """Whether this view represents an actually-held position."""
        return self.quantity > 0


class StrategyParams(BaseModel):
    """Base for a strategy's validated parameter set.

    Concrete strategies subclass this with their own fields and override
    :attr:`required_history`. ``extra='forbid'`` rejects unknown keys so a typo in
    a creation request fails validation rather than being silently ignored.
    """

    model_config = ConfigDict(extra="forbid")

    @property
    def required_history(self) -> int:
        """Number of bars the strategy needs to produce a non-HOLD signal."""
        raise NotImplementedError


@runtime_checkable
class Strategy(Protocol):
    """A pure signal generator. Implementations hold no state and do no I/O."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Return the strategy's :class:`Signal` for the latest bar in ``bars``."""
        ...
