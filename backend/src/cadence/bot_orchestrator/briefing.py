"""The decision briefing an orchestrator run hands to the AI.

Built only from data Cadence already stores, rolled up to market and sector level:

* **market** — technical snapshots computed from the stored daily closes of the
  briefing indices (volume is unavailable for indices, so volume-derived fields are
  omitted);
* **sectors** — per-sector breadth from the latest per-asset indicator snapshots, and
  per-sector news tone aggregated from per-ticker news sentiment;
* **candidates** — the eligible universe equities the AI may choose bot tickers from;
* **presets**, **running bots**, **liquidating bots** and **limits**.

The pure helpers take loaded rows so they are unit-testable; :func:`build_briefing`
does the reads. The result is JSON-serialisable and stored on the run as-is. Missing
inputs are marked ``unavailable`` rather than failing the run.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from statistics import fmean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.assets.market_data import HistoryBar
from cadence.assets.models import Asset
from cadence.bot_orchestrator.constants import BRIEFING_INDICES, MIN_BOT_CAPITAL
from cadence.bot_orchestrator.models import BotOrchestrator
from cadence.bot_orchestrator.service import (
    OrchestratorFigures,
    orchestrator_bots,
    orchestrator_figures,
)
from cadence.news_sentiment.service import resolve_sentiment_annotations
from cadence.paper_trading.constants import BENCHMARK_DISPLAY_NAMES, Benchmark
from cadence.paper_trading.models import BenchmarkPrice
from cadence.strategy_bots import presets
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.constants import STRATEGY_DISPLAY_NAMES, BotSessionStatus
from cadence.strategy_bots.models import BotSession
from cadence.technical_indicators.compute import compute_snapshot
from cadence.technical_indicators.models import TechnicalIndicator

#: Calendar days of index closes loaded (enough for SMA-200 and the 52-week high).
_INDEX_LOOKBACK_DAYS = 400
#: Fewer stored closes than this and an index is reported unavailable.
_MIN_INDEX_CLOSES = 60
#: Sector label for equities without a sector.
UNKNOWN_SECTOR = "unknown"

SentimentResolver = Callable[[Sequence[str]], Mapping[str, Mapping[str, Any]]]


def _r(value: float | None, digits: int = 4) -> float | None:
    """Round for a compact prompt; ``None`` stays ``None``."""
    return None if value is None else round(value, digits)


def _mean(values: Sequence[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return _r(fmean(present)) if present else None


def _share(flags: Sequence[bool]) -> float | None:
    return _r(sum(flags) / len(flags)) if flags else None


# Market ----------------------------------------------------------------------
def index_technicals(
    name: str, closes: Sequence[tuple[date, float]]
) -> dict[str, Any]:
    """A technical snapshot for one index from its stored daily closes."""
    if len(closes) < _MIN_INDEX_CLOSES:
        return {"index": name, "status": "unavailable", "closes": len(closes)}
    bars = [HistoryBar(date=d, close=c, volume=0.0) for d, c in closes]
    snap = compute_snapshot(bars)
    if snap is None:  # pragma: no cover - guarded by the length check
        return {"index": name, "status": "unavailable", "closes": len(closes)}
    return {
        "index": name,
        "status": "available",
        "as_of": snap.trading_date.isoformat(),
        "close": _r(snap.close, 2),
        "sma_50": _r(snap.sma_50, 2),
        "sma_200": _r(snap.sma_200, 2),
        "sma200_slope": _r(snap.sma200_slope),
        "rsi_14": _r(snap.rsi_14, 1),
        "roc_120": _r(snap.roc_120),
        "macd_hist": _r(snap.macd_hist),
        "dist_high_52w": _r(snap.dist_high_52w),
        "drawdown_from_max": _r(snap.drawdown_from_max),
        "hvol_20": _r(snap.hvol_20),
        "regime_pass": snap.gate.regime_pass,
        "momentum_pass": snap.gate.momentum_pass,
    }


# Sectors ---------------------------------------------------------------------
def _sector(asset: Asset) -> str:
    return asset.sector or UNKNOWN_SECTOR


def sector_breadth(
    assets: Sequence[Asset], snapshots: Mapping[int, TechnicalIndicator]
) -> list[dict[str, Any]]:
    """Per-sector breadth from the latest per-asset indicator snapshots.

    Shares and averages are over the equities that have a snapshot; ``equities``
    counts every eligible equity in the sector. Sorted by equity count, then name.
    """
    by_sector: dict[str, list[Asset]] = defaultdict(list)
    for asset in assets:
        by_sector[_sector(asset)].append(asset)
    rows: list[dict[str, Any]] = []
    for sector, members in by_sector.items():
        snaps = [snapshots[a.id] for a in members if a.id in snapshots]
        rows.append(
            {
                "sector": sector,
                "equities": len(members),
                "with_indicators": len(snaps),
                "gate_pass_share": _share([s.gate_pass for s in snaps]),
                "regime_pass_share": _share([s.regime_pass for s in snaps]),
                "avg_rsi_14": _mean([s.rsi_14 for s in snaps]),
                "avg_dist_high_52w": _mean([s.dist_high_52w for s in snaps]),
            }
        )
    return sorted(rows, key=lambda r: (-r["equities"], r["sector"]))


def sector_news_tone(
    assets: Sequence[Asset], annotations: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Per-sector aggregate of the per-ticker news-sentiment signals.

    ``unavailable`` when no ticker has an available signal (e.g. the sentiment
    service is not configured).
    """
    by_sector: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for asset in assets:
        note = annotations.get(asset.ticker)
        if note and note.get("status") == "available":
            by_sector[_sector(asset)].append(note)
    if not by_sector:
        return {"status": "unavailable"}
    sectors = []
    for sector, notes in sorted(by_sector.items()):
        tones = [n.get("tone") for n in notes]
        sectors.append(
            {
                "sector": sector,
                "tickers_with_news": len(notes),
                "avg_score": _mean([n.get("score") for n in notes]),
                "positive": tones.count("positive"),
                "neutral": tones.count("neutral"),
                "negative": tones.count("negative"),
            }
        )
    return {"status": "available", "sectors": sectors}


# Candidates & presets --------------------------------------------------------
def candidate_rows(
    assets: Sequence[Asset],
    snapshots: Mapping[int, TechnicalIndicator],
    annotations: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """One compact row per eligible equity, sorted by ticker."""
    rows: list[dict[str, Any]] = []
    for asset in sorted(assets, key=lambda a: a.ticker):
        snap = snapshots.get(asset.id)
        note = annotations.get(asset.ticker) or {}
        row: dict[str, Any] = {"ticker": asset.ticker, "sector": _sector(asset)}
        if snap is None:
            row["indicators"] = "unavailable"
        else:
            row.update(
                {
                    "gate_pass": snap.gate_pass,
                    "regime_pass": snap.regime_pass,
                    "momentum_pass": snap.momentum_pass,
                    "rsi_14": _r(snap.rsi_14, 1),
                    "roc_120": _r(snap.roc_120),
                    "dist_high_52w": _r(snap.dist_high_52w),
                    "hvol_20": _r(snap.hvol_20),
                }
            )
        if note.get("status") == "available":
            row["news"] = {"tone": note.get("tone"), "score": note.get("score")}
        else:
            row["news"] = "unavailable"
        rows.append(row)
    return rows


def preset_rows() -> list[dict[str, Any]]:
    """Every catalog preset the AI may deploy."""
    return [
        {
            "key": p.key,
            "name": p.display_name,
            "strategy": STRATEGY_DISPLAY_NAMES[p.strategy_key],
            "course_ref": p.course_ref,
            "description": p.description,
            "take_profit_pct": p.take_profit_pct,
            "stop_loss_pct": p.stop_loss_pct,
            "drawdown_stop_pct": p.drawdown_stop_pct,
        }
        for p in presets.list_presets()
    ]


# Bots & limits ---------------------------------------------------------------
def running_bot_row(
    db: Session, bot: BotSession, *, now: datetime
) -> dict[str, Any]:
    """An active bot with its performance (the AI may choose to stop it)."""
    kpis = bot_service.bot_session_kpis(db, bot)
    round_trips = bot_service.bot_round_trips(db, bot)
    wins = sum(1 for t in round_trips if t.realised_pnl > 0)
    return {
        "bot_id": str(bot.id),
        "preset_key": bot.preset_key,
        "tickers": [s.ticker for s in bot.symbols],
        "days_active": max((now - bot.created_at).days, 0),
        "allocated_capital": _r(bot.initial_capital, 2),
        "current_value": _r(kpis.current_value, 2),
        "total_return_pct": _r(kpis.total_return_pct),
        "max_drawdown": _r(kpis.max_drawdown),
        "open_positions": len(bot.positions),
        "closed_trades": len(round_trips),
        "win_rate": _r(wins / len(round_trips)) if round_trips else None,
    }


def limit_block(
    orchestrator: BotOrchestrator, figures: OrchestratorFigures
) -> dict[str, Any]:
    """The limits every deploy must respect at decision time."""
    per_bot_cap = orchestrator.max_bot_share * figures.value
    return {
        "orchestrator_value": _r(figures.value, 2),
        "free_capital": _r(orchestrator.free_capital, 2),
        "max_parallel_bots": orchestrator.max_parallel_bots,
        "active_bots": figures.active_bots,
        "open_slots": max(orchestrator.max_parallel_bots - figures.active_bots, 0),
        "min_bot_capital": MIN_BOT_CAPITAL,
        "max_bot_capital": _r(per_bot_cap, 2),
        "max_tickers_per_bot": orchestrator.max_tickers_per_bot,
    }


# Assembly --------------------------------------------------------------------
def _index_closes(db: Session, benchmark: Benchmark, now: datetime) -> list[tuple[date, float]]:
    since = date.fromordinal(now.date().toordinal() - _INDEX_LOOKBACK_DAYS)
    stmt = (
        select(BenchmarkPrice.price_date, BenchmarkPrice.close)
        .where(BenchmarkPrice.benchmark == benchmark.value)
        .where(BenchmarkPrice.price_date >= since)
        .order_by(BenchmarkPrice.price_date)
    )
    return [(d, float(c)) for d, c in db.execute(stmt).all()]


def build_briefing(
    db: Session,
    orchestrator: BotOrchestrator,
    *,
    now: datetime,
    resolve_sentiment: SentimentResolver = resolve_sentiment_annotations,
) -> dict[str, Any]:
    """Assemble the full decision briefing for one run."""
    assets = bot_service.resolve_universe_equities(db)
    snapshots = {
        row.asset_id: row
        for row in db.execute(
            select(TechnicalIndicator).where(
                TechnicalIndicator.asset_id.in_([a.id for a in assets])
            )
        ).scalars()
    }
    annotations = resolve_sentiment([a.ticker for a in assets])
    figures = orchestrator_figures(db, orchestrator)
    bots = orchestrator_bots(db, orchestrator)
    active = [b for b in bots if b.status == BotSessionStatus.ACTIVE.value]
    liquidating = [
        b for b in bots if b.status != BotSessionStatus.ACTIVE.value and b.positions
    ]
    return {
        "as_of": now.isoformat(),
        "market": [
            index_technicals(
                BENCHMARK_DISPLAY_NAMES[index], _index_closes(db, index, now)
            )
            for index in BRIEFING_INDICES
        ],
        "sectors": {
            "breadth": sector_breadth(assets, snapshots),
            "news_tone": sector_news_tone(assets, annotations),
        },
        "candidates": candidate_rows(assets, snapshots, annotations),
        "presets": preset_rows(),
        "running_bots": [running_bot_row(db, b, now=now) for b in active],
        "liquidating_bots": [
            {
                "bot_id": str(b.id),
                "preset_key": b.preset_key,
                "tickers": [s.ticker for s in b.symbols],
                "open_positions": len(b.positions),
            }
            for b in liquidating
        ],
        "limits": limit_block(orchestrator, figures),
    }
