"""The VAMA strategy — a long-only volatility-adaptive moving-average signal.

Ported from the course "Algo 30 VAMA – Volatility Adaptive Moving Average". The VAMA is a
moving average updated as α × close + (1 − α) × previous, where the smoothing factor α
depends on volatility. Enter long when the close is above the VAMA; exit when it falls to
or below it. The course short leg is dropped (Cadence is long-only); there is no
take-profit / stop-loss in the course, the drawdown kill-switch stays with the engine.

Two smoothing modes:

* **Fixed** (``adaptive`` off — the course): the course divides the current volatility by
  itself, so its "adaptive" ratio is always 1 and α is always ``alpha_max`` (``alpha_min``
  when prices are flat). This mode reproduces that exactly.
* **Adaptive** (``adaptive`` on): α = ``alpha_max`` × current ÷ average volatility, clamped
  to [``alpha_min``, ``alpha_max``] — current volatility is the population standard
  deviation of the latest ``lookback`` closes, average volatility the mean of that value
  over the latest ``lookback`` bars. Normal volatility gives ``alpha_max``; calmer markets
  slow the average down.

The VAMA is path-dependent, so it is replayed over the bars provided, oldest first. Pure
and deterministic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import Field, model_validator

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)


class VamaParams(StrategyParams):
    """Parameters for :class:`VamaStrategy`. Defaults match course Algo 30."""

    lookback: int = Field(default=20, ge=2)
    alpha_min: float = Field(default=0.02, gt=0.0, le=1.0)
    alpha_max: float = Field(default=0.20, gt=0.0, le=1.0)
    adaptive: bool = False

    @model_validator(mode="after")
    def _min_below_max(self) -> VamaParams:
        if self.alpha_min >= self.alpha_max:
            raise ValueError("alpha_min must be less than alpha_max")
        return self

    @property
    def required_history(self) -> int:
        """Bars until α is defined plus a replay span for the VAMA to settle."""
        return (5 if self.adaptive else 4) * self.lookback


def _pstd(values: Sequence[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def smoothing_factors(closes: Sequence[float], params: VamaParams) -> list[float | None]:
    """α for every close (``None`` while it is not yet defined)."""
    n = params.lookback
    vols: list[float | None] = [
        _pstd(closes[i - n + 1 : i + 1]) if i >= n - 1 else None for i in range(len(closes))
    ]
    alphas: list[float | None] = []
    for i, vol in enumerate(vols):
        if vol is None:
            alphas.append(None)
        elif not params.adaptive:
            alphas.append(params.alpha_max if vol > 0 else params.alpha_min)
        elif i < 2 * n - 2:
            alphas.append(None)
        else:
            window = [v for v in vols[i - n + 1 : i + 1] if v is not None]
            average = sum(window) / len(window)
            if average <= 0:
                alphas.append(params.alpha_min)
            else:
                raw = params.alpha_max * vol / average
                alphas.append(min(params.alpha_max, max(params.alpha_min, raw)))
    return alphas


def vama(closes: Sequence[float], params: VamaParams) -> float | None:
    """The VAMA at the latest close, replayed from the first bar where α is defined."""
    value: float | None = None
    for close, alpha in zip(closes, smoothing_factors(closes, params), strict=True):
        if alpha is None:
            continue
        value = close if value is None else alpha * close + (1 - alpha) * value
    return value


class VamaStrategy:
    """Volatility-adaptive moving-average signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Enter above the VAMA; exit at or below it."""
        if not isinstance(params, VamaParams):
            raise TypeError(f"VamaStrategy requires VamaParams, got {type(params).__name__}")
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the VAMA")

        closes = [bar.close for bar in bars]
        line = vama(closes, params)
        if line is None:  # pragma: no cover - guarded by required_history
            return Signal.hold("insufficient history for the VAMA")
        close = closes[-1]
        mode = "adaptive" if params.adaptive else "fixed"
        if position is not None and position.is_open:
            if close <= line:
                return Signal.exit(f"close {close:g} at or below the {mode} VAMA {line:.4g}")
            return Signal.hold(f"close {close:g} above the {mode} VAMA {line:.4g}")
        if close > line:
            return Signal.enter_long(f"close {close:g} above the {mode} VAMA {line:.4g}")
        return Signal.hold(f"close {close:g} at or below the {mode} VAMA {line:.4g}")
