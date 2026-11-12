"""The Trend Confirmation strategy — a long-only AND of intraday trend legs.

Cadence's own design (roadmap #13, not a course port), derived from the AI portfolio's
technical trend gate and re-tuned for the bots' intraday bars. It shares the gate's
indicator maths (:mod:`cadence.technical_indicators.series`):

* **Trend** — fast SMA above the slow SMA;
* **Momentum** — MACD histogram above 0;
* **Strength** — RSI above ``rsi_entry`` but below the ``rsi_max`` cap (not exhausted);
* optional **ROC** — rate of change over ``roc_period`` bars above 0;
* optional **OBV** — on-balance volume rising over ``obv_window`` bars.

It enters long only when **every** active leg agrees and exits as soon as **any** breaks.
To keep 5-minute noise from churning positions, the RSI leg exits only below a lower
``rsi_exit`` level (hysteresis) and never because the RSI is above the cap — strength is
not a reason to sell. Take-profit, stop-loss and the drawdown kill-switch stay with the
engine. Pure and deterministic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd
from pydantic import Field, model_validator

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)
from cadence.technical_indicators import series


class TrendConfirmationParams(StrategyParams):
    """Parameters for :class:`TrendConfirmationStrategy` (Cadence's intraday defaults)."""

    sma_fast: int = Field(default=20, ge=2)
    sma_slow: int = Field(default=50, ge=3)
    macd_fast: int = Field(default=12, ge=2)
    macd_slow: int = Field(default=26, ge=3)
    macd_signal: int = Field(default=9, ge=2)
    rsi_period: int = Field(default=14, ge=2)
    rsi_entry: float = Field(default=50.0, ge=0.0, lt=100.0)
    rsi_max: float = Field(default=70.0, gt=0.0, le=100.0)
    rsi_exit: float = Field(default=45.0, ge=0.0, lt=100.0)
    use_roc: bool = False
    roc_period: int = Field(default=12, ge=1)
    use_obv: bool = False
    obv_window: int = Field(default=20, ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> TrendConfirmationParams:
        if self.sma_fast >= self.sma_slow:
            raise ValueError("sma_fast must be less than sma_slow")
        if self.macd_fast >= self.macd_slow:
            raise ValueError("macd_fast must be less than macd_slow")
        if not self.rsi_exit <= self.rsi_entry < self.rsi_max:
            raise ValueError("RSI levels must satisfy rsi_exit <= rsi_entry < rsi_max")
        return self

    @property
    def required_history(self) -> int:
        """A fixed span over which the EMA- and Wilder-based series have converged."""
        return max(
            self.sma_slow,
            3 * self.macd_slow + self.macd_signal,
            3 * self.rsi_period,
            self.roc_period + 1,
            self.obv_window + 1,
        )


def _latest(values: pd.Series) -> float | None:
    if values.empty:
        return None
    value = float(values.iloc[-1])
    return None if math.isnan(value) or math.isinf(value) else value


class TrendConfirmationStrategy:
    """Multi-leg trend confirmation signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Enter when every active leg agrees; exit when any active leg breaks."""
        if not isinstance(params, TrendConfirmationParams):
            raise TypeError(
                "TrendConfirmationStrategy requires TrendConfirmationParams, got "
                f"{type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the trend legs")

        close = pd.Series([bar.close for bar in bars], dtype="float64")
        values: dict[str, float | None] = {
            "sma_fast": _latest(series.sma(close, params.sma_fast)),
            "sma_slow": _latest(series.sma(close, params.sma_slow)),
            "macd_hist": _latest(
                series.macd(close, params.macd_fast, params.macd_slow, params.macd_signal).histogram
            ),
            "rsi": _latest(series.rsi(close, params.rsi_period)),
        }
        if params.use_roc:
            values["roc"] = _latest(series.roc(close, params.roc_period))
        if params.use_obv:
            volume = pd.Series([bar.volume for bar in bars], dtype="float64")
            values["obv_change"] = _latest(
                series.change(series.obv(close, volume), params.obv_window)
            )
        if any(v is None for v in values.values()):
            missing = ", ".join(k for k, v in values.items() if v is None)
            return Signal.hold(f"indicator not available yet: {missing}")
        v: dict[str, float] = {k: float(x) for k, x in values.items() if x is not None}

        if position is not None and position.is_open:
            broken = []
            if v["sma_fast"] < v["sma_slow"]:
                broken.append("fast SMA below slow SMA")
            if v["macd_hist"] < 0:
                broken.append("MACD histogram negative")
            if v["rsi"] < params.rsi_exit:
                broken.append(f"RSI {v['rsi']:.1f} below {params.rsi_exit:g}")
            if params.use_roc and v["roc"] < 0:
                broken.append("rate of change negative")
            if params.use_obv and v["obv_change"] < 0:
                broken.append("OBV falling")
            if broken:
                return Signal.exit("trend leg broken: " + "; ".join(broken))
            return Signal.hold("all trend legs still intact")

        failing = []
        if not v["sma_fast"] > v["sma_slow"]:
            failing.append("fast SMA not above slow SMA")
        if not v["macd_hist"] > 0:
            failing.append("MACD histogram not positive")
        if not params.rsi_entry < v["rsi"] < params.rsi_max:
            failing.append(f"RSI {v['rsi']:.1f} outside {params.rsi_entry:g}–{params.rsi_max:g}")
        if params.use_roc and not v["roc"] > 0:
            failing.append("rate of change not positive")
        if params.use_obv and not v["obv_change"] > 0:
            failing.append("OBV not rising")
        if failing:
            return Signal.hold("not every leg agrees: " + "; ".join(failing))
        return Signal.enter_long(
            f"all trend legs agree (RSI {v['rsi']:.1f}, MACD histogram {v['macd_hist']:.3g})"
        )
