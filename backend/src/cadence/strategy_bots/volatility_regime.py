"""The Volatility Regime Switcher strategy — long-only, trend or reversion by volatility.

Ported from the course "Algo 20 Volatility Regime Switcher". Volatility is the course ATR
proxy — the mean absolute close-to-close change over the latest ``atr_window`` closes (as
the ATR-Band bot uses). It is compared with a baseline:

* **calm** (ATR at or below the baseline) → **trend** mode: enter long when the close is
  above HL2, the midpoint of the highest and lowest of the latest ``atr_window`` closes;
  exit when it falls below HL2.
* **volatile** (ATR above the baseline) → **reversion** mode: enter long when the close is
  below SMA(``sma_period``) × (1 − ``reversion_deviation``); exit when it is back at or above
  the SMA.

The course freezes its baseline from the first prices after start-up; Cadence is stateless,
so the baseline is the average of the rolling ATR over the latest ``baseline_bars`` bars.
Exits follow the regime of the latest bar, as in the course. The course short legs are
dropped (Cadence is long-only); take-profit, stop-loss and the drawdown kill-switch stay
with the engine. Pure and deterministic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import Field

from cadence.strategy_bots.atr_band_trend import mean_abs_close_change
from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)

Regime = Literal["trend", "reversion"]


class VolatilityRegimeParams(StrategyParams):
    """Parameters for :class:`VolatilityRegimeStrategy`. Defaults match course Algo 20."""

    atr_window: int = Field(default=20, ge=2)
    sma_period: int = Field(default=20, ge=2)
    baseline_bars: int = Field(default=100, ge=2)
    reversion_deviation: float = Field(default=0.0, ge=0.0, lt=1.0)

    @property
    def required_history(self) -> int:
        """Every ATR in the baseline needs its full window; the SMA needs its period."""
        return max(self.baseline_bars + self.atr_window - 1, self.sma_period)


def rolling_atr(closes: Sequence[float], window: int, count: int) -> list[float]:
    """The ATR at each of the latest ``count`` bars (oldest first)."""
    end = len(closes)
    return [mean_abs_close_change(closes[i - window + 1 : i + 1]) for i in range(end - count, end)]


def regime(closes: Sequence[float], params: VolatilityRegimeParams) -> tuple[Regime, float, float]:
    """The latest bar's regime with its ATR and baseline."""
    atrs = rolling_atr(closes, params.atr_window, params.baseline_bars)
    atr, baseline = atrs[-1], sum(atrs) / len(atrs)
    return ("trend" if atr <= baseline else "reversion"), atr, baseline


class VolatilityRegimeStrategy:
    """Volatility regime switching signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Trend rule in calm markets, reversion rule in volatile ones."""
        if not isinstance(params, VolatilityRegimeParams):
            raise TypeError(
                "VolatilityRegimeStrategy requires VolatilityRegimeParams, got "
                f"{type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the volatility baseline")

        closes = [bar.close for bar in bars]
        close = closes[-1]
        mode, atr, baseline = regime(closes, params)
        context = f"ATR {atr:.4g} vs baseline {baseline:.4g}"
        holding = position is not None and position.is_open

        if mode == "trend":
            window = closes[-params.atr_window :]
            hl2 = (max(window) + min(window)) / 2
            summary = f"calm ({context}): close {close:g} vs HL2 {hl2:.4g}"
            if holding:
                if close < hl2:
                    return Signal.exit(f"trend broke below HL2 — {summary}")
                return Signal.hold(f"trend intact — {summary}")
            if close > hl2:
                return Signal.enter_long(f"trend above HL2 — {summary}")
            return Signal.hold(f"no trend entry — {summary}")

        sma = sum(closes[-params.sma_period :]) / params.sma_period
        threshold = sma * (1 - params.reversion_deviation)
        summary = f"volatile ({context}): close {close:g} vs SMA {sma:.4g}"
        if holding:
            if close >= sma:
                return Signal.exit(f"reverted to the SMA — {summary}")
            return Signal.hold(f"not yet reverted — {summary}")
        if close < threshold:
            return Signal.enter_long(f"dip below the SMA — {summary}")
        return Signal.hold(f"no reversion entry — {summary}")
