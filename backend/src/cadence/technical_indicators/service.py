"""Compute-and-store service for technical indicators.

The nightly runner iterates every asset in the universe, fetches its price history
from the market-data provider, computes the latest :class:`IndicatorSnapshot`, and
upserts the single ``technical_indicator`` row for that asset (delete-then-insert),
committing per asset so a mid-run failure keeps prior work. A
``technical_indicator_run`` audit row records status, timing, and processed/failed
counts. Per-asset failures are counted and the run continues; an unexpected
top-level failure marks the run failed.

Reads (:func:`get_latest_snapshot`, :func:`get_latest_snapshots`) return the
stored rows for the trading flows to consume — the trading path never computes
inline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cadence.assets.market_data import MarketDataProvider
from cadence.assets.models import Asset
from cadence.technical_indicators import constants as c
from cadence.technical_indicators.compute import IndicatorSnapshot, compute_snapshot
from cadence.technical_indicators.constants import RunPhase
from cadence.technical_indicators.models import (
    TechnicalIndicator,
    TechnicalIndicatorRun,
)

logger = logging.getLogger(__name__)


# --- Read-only configuration projection -------------------------------------
# The trend strategy's indicator set, gate rules, and reversal-flag definitions
# live in constants.py. The dataclasses below project that configuration into a
# self-describing, display-ready structure (labels + numeric values sourced from
# the constants, never duplicated) that the read endpoint serves verbatim.


@dataclass(frozen=True)
class IndicatorParam:
    """One period/lookback parameter defining an indicator."""

    name: str
    value: int | float


@dataclass(frozen=True)
class IndicatorInfo:
    """A single indicator in the computed set with its defining parameters."""

    key: str
    label: str
    params: tuple[IndicatorParam, ...]


@dataclass(frozen=True)
class GateCondition:
    """One condition of the trend gate; ``threshold`` is absent for comparisons
    between two indicators (e.g. SMA50 > SMA200)."""

    description: str
    threshold: float | None


@dataclass(frozen=True)
class TrendGateInfo:
    """The deterministic uptrend gate: its regime and momentum conditions, the
    soft OBV bonus, and the missing-indicator rule."""

    description: str
    regime: tuple[GateCondition, ...]
    momentum: tuple[GateCondition, ...]
    obv_bonus: str
    missing_indicator_rule: str


@dataclass(frozen=True)
class ReversalFlagInfo:
    """One reversal flag and what sets it."""

    key: str
    label: str
    description: str


@dataclass(frozen=True)
class ReversalFlagsInfo:
    """The reversal-flag definitions plus their tunable thresholds."""

    flags: tuple[ReversalFlagInfo, ...]
    rsi_overbought: float
    slope_flatten_eps: float


@dataclass(frozen=True)
class IndicatorConfig:
    """The full read-only technical-indicator configuration."""

    indicators: tuple[IndicatorInfo, ...]
    trend_gate: TrendGateInfo
    reversal_flags: ReversalFlagsInfo


def get_indicator_config() -> IndicatorConfig:
    """Project the configured indicator set, trend gate, and reversal flags.

    Pure (no DB access): every numeric value is read from :mod:`constants` so the
    result always reflects the live configuration rather than a duplicated copy.
    """
    indicators = (
        IndicatorInfo(
            "sma_50",
            "Simple moving average (short)",
            (IndicatorParam("period", c.SMA_SHORT),),
        ),
        IndicatorInfo(
            "sma_200",
            "Simple moving average (long)",
            (IndicatorParam("period", c.SMA_LONG),),
        ),
        IndicatorInfo("close_sma200", "Price / SMA200 ratio", ()),
        IndicatorInfo("sma50_sma200", "SMA50 / SMA200 ratio", ()),
        IndicatorInfo(
            "sma200_slope",
            "SMA200 slope",
            (IndicatorParam("window", c.SLOPE_WINDOW),),
        ),
        IndicatorInfo(
            "ema_20",
            "Exponential moving average",
            (IndicatorParam("span", c.EMA_SPAN),),
        ),
        IndicatorInfo(
            "macd",
            "MACD (line / signal / histogram)",
            (
                IndicatorParam("fast", c.MACD_FAST),
                IndicatorParam("slow", c.MACD_SLOW),
                IndicatorParam("signal", c.MACD_SIGNAL),
            ),
        ),
        IndicatorInfo(
            "rsi_14", "Wilder RSI", (IndicatorParam("period", c.RSI_PERIOD),)
        ),
        IndicatorInfo(
            "roc_120", "Rate of change", (IndicatorParam("period", c.ROC_PERIOD),)
        ),
        IndicatorInfo("obv", "On-balance volume (OBV)", ()),
        IndicatorInfo(
            "obv_change_20d",
            "OBV change",
            (IndicatorParam("window", c.OBV_CHANGE_WINDOW),),
        ),
        IndicatorInfo(
            "vol_ratio_50",
            "Volume ratio vs average volume",
            (IndicatorParam("period", c.AVG_VOL_PERIOD),),
        ),
        IndicatorInfo(
            "dist_high_52w",
            "Distance from 52-week high",
            (IndicatorParam("period", c.HIGH_52W),),
        ),
        IndicatorInfo(
            "drawdown_from_max",
            "Drawdown from trailing max",
            (IndicatorParam("period", c.DRAWDOWN_PERIOD),),
        ),
        IndicatorInfo(
            "hvol_20",
            "Historical volatility (annualised)",
            (
                IndicatorParam("period", c.HVOL_PERIOD),
                IndicatorParam("trading_days", c.TRADING_DAYS),
            ),
        ),
        IndicatorInfo(
            "bb_pctb",
            "Bollinger %b",
            (
                IndicatorParam("period", c.BB_PERIOD),
                IndicatorParam("std", c.BB_STD),
            ),
        ),
        IndicatorInfo(
            "bb_width",
            "Bollinger bandwidth",
            (
                IndicatorParam("period", c.BB_PERIOD),
                IndicatorParam("std", c.BB_STD),
            ),
        ),
    )
    trend_gate = TrendGateInfo(
        description=(
            "Deterministic uptrend verdict. The gate passes only when BOTH the "
            "regime and the momentum checks pass."
        ),
        regime=(
            GateCondition("Latest close is above the 200-day SMA", None),
            GateCondition("SMA50 is above SMA200", None),
            GateCondition(
                f"SMA200 slope is at least {c.SMA_SLOPE_MIN}", c.SMA_SLOPE_MIN
            ),
        ),
        momentum=(
            GateCondition(
                f"MACD histogram is above {c.MACD_HIST_MIN}", c.MACD_HIST_MIN
            ),
            GateCondition(
                f"Wilder RSI is above {c.RSI_MOMENTUM_MIN}", c.RSI_MOMENTUM_MIN
            ),
            GateCondition(
                f"Rate of change (120d) is above {c.ROC_MOMENTUM_MIN}",
                c.ROC_MOMENTUM_MIN,
            ),
        ),
        obv_bonus=(
            "Rising 20-day OBV is a soft confirmation signal only — it is not "
            "required for the gate to pass."
        ),
        missing_indicator_rule=(
            "If any indicator a check requires is unavailable (insufficient "
            "history), that check fails and the gate does not pass."
        ),
    )
    reversal_flags = ReversalFlagsInfo(
        flags=(
            ReversalFlagInfo(
                "macd_hist_rollover",
                "MACD histogram rollover",
                "The MACD histogram turned down versus the prior bar.",
            ),
            ReversalFlagInfo(
                "rsi_rollover",
                "RSI rollover",
                f"RSI was at or above {c.RSI_OVERBOUGHT} (overbought) and turned "
                "down.",
            ),
            ReversalFlagInfo(
                "return_decel",
                "Return deceleration",
                "5-day return acceleration is non-positive — momentum is fading.",
            ),
            ReversalFlagInfo(
                "obv_price_divergence",
                "OBV / price divergence",
                f"Price printed a new {c.DIVERGENCE_LOOKBACK}-day high but OBV did "
                "not confirm it.",
            ),
            ReversalFlagInfo(
                "sma200_slope_flattening",
                "SMA200 slope flattening",
                f"SMA200 slope fell below {c.SLOPE_FLATTEN_EPS} (near-zero or "
                "declining).",
            ),
        ),
        rsi_overbought=c.RSI_OVERBOUGHT,
        slope_flatten_eps=c.SLOPE_FLATTEN_EPS,
    )
    return IndicatorConfig(
        indicators=indicators,
        trend_gate=trend_gate,
        reversal_flags=reversal_flags,
    )


def create_run(session: Session) -> TechnicalIndicatorRun:
    """Create and persist a queued run-audit row."""
    run = TechnicalIndicatorRun(status=RunPhase.QUEUED.value)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_run(session: Session, run_id: int) -> TechnicalIndicatorRun | None:
    return session.get(TechnicalIndicatorRun, run_id)


def get_latest_snapshot(
    session: Session, asset_id: int
) -> TechnicalIndicator | None:
    """Return the stored snapshot for one asset, or ``None`` if not computed."""
    return session.execute(
        select(TechnicalIndicator).where(TechnicalIndicator.asset_id == asset_id)
    ).scalar_one_or_none()


def get_latest_snapshots(
    session: Session, asset_ids: list[int]
) -> dict[int, TechnicalIndicator]:
    """Return stored snapshots keyed by asset id (missing ids simply absent)."""
    if not asset_ids:
        return {}
    rows = session.execute(
        select(TechnicalIndicator).where(TechnicalIndicator.asset_id.in_(asset_ids))
    ).scalars()
    return {row.asset_id: row for row in rows}


def _snapshot_to_row(asset_id: int, snapshot: IndicatorSnapshot) -> TechnicalIndicator:
    gate = snapshot.gate
    flags = snapshot.reversal_flags
    return TechnicalIndicator(
        asset_id=asset_id,
        trading_date=snapshot.trading_date,
        close=snapshot.close,
        sma_50=snapshot.sma_50,
        sma_200=snapshot.sma_200,
        close_sma200=snapshot.close_sma200,
        sma50_sma200=snapshot.sma50_sma200,
        sma200_slope=snapshot.sma200_slope,
        ema_20=snapshot.ema_20,
        macd_line=snapshot.macd_line,
        macd_signal=snapshot.macd_signal,
        macd_hist=snapshot.macd_hist,
        rsi_14=snapshot.rsi_14,
        roc_120=snapshot.roc_120,
        obv=snapshot.obv,
        obv_change_20d=snapshot.obv_change_20d,
        vol_ratio_50=snapshot.vol_ratio_50,
        dist_high_52w=snapshot.dist_high_52w,
        drawdown_from_max=snapshot.drawdown_from_max,
        hvol_20=snapshot.hvol_20,
        bb_pctb=snapshot.bb_pctb,
        bb_width=snapshot.bb_width,
        gate_pass=gate.gate_pass,
        regime_pass=gate.regime_pass,
        momentum_pass=gate.momentum_pass,
        obv_rising=gate.obv_rising,
        rev_macd_hist_rollover=flags.macd_hist_rollover,
        rev_rsi_rollover=flags.rsi_rollover,
        rev_return_decel=flags.return_decel,
        rev_obv_price_divergence=flags.obv_price_divergence,
        rev_sma200_slope_flattening=flags.sma200_slope_flattening,
    )


def compute_and_store(
    session: Session,
    asset: Asset,
    provider: MarketDataProvider,
) -> bool:
    """Compute and upsert the latest snapshot for one asset.

    Replaces the asset's existing row (delete-then-insert) and commits. Returns
    ``True`` when a snapshot was stored, ``False`` when the provider returned no
    history (nothing to store). Exceptions propagate to the caller, which counts
    the asset as failed.
    """
    bars = provider.fetch_history(asset.ticker)
    snapshot = compute_snapshot(bars)
    if snapshot is None:
        return False
    session.execute(
        delete(TechnicalIndicator).where(TechnicalIndicator.asset_id == asset.id)
    )
    session.add(_snapshot_to_row(asset.id, snapshot))
    session.commit()
    return True


def execute_run(
    session: Session,
    run_id: int,
    provider: MarketDataProvider,
) -> TechnicalIndicatorRun:
    """Run the indicator precompute over the whole universe.

    Marks the run running, iterates every asset committing per asset, counts
    per-asset failures without aborting the run, and marks the run completed. An
    unexpected top-level failure marks the run failed and re-raises.
    """
    run = session.get(TechnicalIndicatorRun, run_id)
    if run is None:
        raise ValueError(f"technical_indicator_run {run_id} not found")

    run.status = RunPhase.RUNNING.value
    run.started_at = datetime.now(UTC)
    session.commit()

    processed = 0
    failed = 0
    try:
        assets = list(session.execute(select(Asset)).scalars())
        for asset in assets:
            try:
                compute_and_store(session, asset, provider)
                processed += 1
            except Exception:
                session.rollback()
                failed += 1
                logger.exception(
                    "technical-indicator compute failed for %s", asset.ticker
                )
        run = session.get(TechnicalIndicatorRun, run_id)
        assert run is not None
        run.status = RunPhase.COMPLETED.value
        run.finished_at = datetime.now(UTC)
        run.assets_processed = processed
        run.assets_failed = failed
        session.commit()
        return run
    except Exception as exc:
        session.rollback()
        run = session.get(TechnicalIndicatorRun, run_id)
        if run is not None:
            run.status = RunPhase.FAILED.value
            run.finished_at = datetime.now(UTC)
            run.assets_processed = processed
            run.assets_failed = failed
            run.error = f"{type(exc).__name__}: {exc}"
            session.commit()
        raise
