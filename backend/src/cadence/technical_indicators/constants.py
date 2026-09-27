"""Indicator periods, gate thresholds, and run-lifecycle constants.

All thresholds are plain module constants so they can be tuned without a schema
or prompt change (design decision: "thresholds as constants").
"""

from __future__ import annotations

from enum import StrEnum

# --- Indicator periods (close+volume subset) -------------------------------
SMA_SHORT = 50
SMA_LONG = 200
EMA_SPAN = 20
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
RSI_PERIOD = 14
ROC_PERIOD = 120
BB_PERIOD = 20
BB_STD = 2.0
HVOL_PERIOD = 20
AVG_VOL_PERIOD = 50
HIGH_52W = 252
DRAWDOWN_PERIOD = 252

#: Lookback (bars) for the SMA200 slope (percent change over the window).
SLOPE_WINDOW = 20
#: Lookback (bars) for the OBV change and the OBV/price divergence proxy.
OBV_CHANGE_WINDOW = 20
DIVERGENCE_LOOKBACK = 20

#: Trading days per year, for annualising historical volatility.
TRADING_DAYS = 252

# --- Deterministic uptrend gate thresholds (tunable) -----------------------
#: Regime: close > SMA200 AND SMA50 > SMA200 AND SMA200 slope >= this.
SMA_SLOPE_MIN = 0.0
#: Momentum: MACD histogram strictly above this.
MACD_HIST_MIN = 0.0
#: Momentum: RSI(14) strictly above this.
RSI_MOMENTUM_MIN = 50.0
#: Momentum: ROC(120) strictly above this.
ROC_MOMENTUM_MIN = 0.0

# --- Reversal-flag thresholds (tunable) ------------------------------------
#: RSI band above which a turn-down counts as an RSI rollover.
RSI_OVERBOUGHT = 70.0
#: SMA200 slope below this counts as "flattening" (covers near-zero/declining).
SLOPE_FLATTEN_EPS = 0.005


class RunPhase(StrEnum):
    """Lifecycle of a technical-indicator precompute run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


#: Phases from which a run never transitions again.
TERMINAL_PHASES = frozenset({RunPhase.COMPLETED, RunPhase.FAILED})
