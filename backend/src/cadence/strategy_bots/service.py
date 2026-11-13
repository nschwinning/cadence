"""Session service and tick runner for the strategy-bot subsystem.

Business logic + DB access for bot sessions: CRUD/lifecycle, the stateless-recompute
tick, daily value snapshots, and KPIs. This module is the single entry point the
router and the dashboard adapter depend on; it reads the shared universe through
``assets_service`` (seam 1) and executes through the :class:`Broker` /
:class:`MarketData` protocols so tests can inject fakes.

The tick is deliberately stateless: nothing is cached across ticks in the runner —
position state, the trade ledger, and value snapshots live in the database, so the
process is crash-safe and restartable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from itertools import pairwise
from typing import Final, Literal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cadence import database
from cadence.agents import llm_trace
from cadence.assets import service as assets_service
from cadence.assets.category import AssetCategory, AssetMembership
from cadence.assets.models import Asset
from cadence.broker.base import Broker, BrokerError
from cadence.broker.models import AssetClass, OrderSide
from cadence.config import settings
from cadence.dashboard.constants import DashboardRange, resolve_range_start
from cadence.dashboard.service import (
    SessionContribution,
    SessionPerformance,
    SessionValuePoint,
)
from cadence.notify.base import Notifier
from cadence.orders.models import OrderOwnerKind
from cadence.orders.reconcile import reconcile_orders
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.benchmark import (
    Contribution,
    benchmark_return_fraction,
    load_benchmark_series,
    rebased_benchmark_value,
)
from cadence.paper_trading.constants import (
    SHARPE_TRADING_DAYS_PER_YEAR,
    Benchmark,
    benchmark_display_name,
)
from cadence.strategy_bots import presets, registry
from cadence.strategy_bots.constants import (
    BotOrigin,
    BotSessionStatus,
    BotValueResolution,
    SizingMethod,
    StopReason,
)
from cadence.strategy_bots.engine import (
    REASON_DRAWDOWN,
    REASON_SESSION_STOPPED,
    ExecutionEngine,
    take_profit_stop_loss_reason,
    total_value,
    unrealised_pnl,
)
from cadence.strategy_bots.errors import (
    BotSessionNotArchivableError,
    BotSessionNotFoundError,
    BotSessionNotStoppedError,
    BotSummaryUnavailableError,
    IneligibleAssetError,
    InvalidBotBenchmarkError,
    InvalidBotConfigError,
    UnknownPresetError,
)
from cadence.strategy_bots.market_data import MarketData
from cadence.strategy_bots.models import (
    BotSession,
    BotSymbol,
    BotTickRun,
    BotTrade,
    BotValuePoint,
    BotValueSnapshot,
)
from cadence.strategy_bots.notifications import (
    _bot_summary_message,
    _kill_switch_message,
    _notify_safely,
    _signed_pct,
)
from cadence.strategy_bots.presets import BotPreset
from cadence.strategy_bots.sizing import (
    EntryCandidate,
    atr,
    plan_entries,
)
from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    SignalAction,
    StrategyParams,
)
from cadence.strategy_bots.summary_agent import (
    BotSessionSummaryAgent,
    get_bot_summary_model,
)

_logger = logging.getLogger(__name__)

#: Stored tick/bot error messages are truncated to this many characters.
_FAILURE_MESSAGE_MAX = 500


class _Unset(Enum):
    """Sentinel type for "not supplied" on preset-overridable creation inputs."""

    TOKEN = 0


#: Marks a preset-overridable creation input as not supplied, so the preset's value
#: applies. Distinct from ``None``, which explicitly turns take-profit / stop-loss off.
UNSET: Final = _Unset.TOKEN


@dataclass(frozen=True)
class TickResult:
    """Summary of one tick run."""

    market_open: bool
    #: Active sessions that were evaluated and had the engine applied.
    processed: int = 0
    #: Active sessions skipped because fresh bars were unavailable.
    skipped: int = 0
    #: Positions of stopped / archived sessions sold to flatten them this tick.
    flattened: int = 0
    #: Sessions whose processing raised this tick (their own work rolled back only).
    failed: int = 0
    #: Unrecorded orders booked by the reconciliation pass that opens the tick.
    reconciled: int = 0


@dataclass(frozen=True)
class SnapshotResult:
    """Summary of one daily snapshot run."""

    #: Active sessions snapshotted.
    snapshots: int = 0
    #: Unrecorded bot orders booked by the reconciliation pass that opens the run.
    reconciled: int = 0


@dataclass(frozen=True)
class BotValueHistoryPoint:
    """One timestamped point of a bot session's value history at some resolution.

    Resolution-agnostic: intraday points carry their ``bot_value_points.captured_at``;
    daily/monthly points carry an end-of-day timestamp derived from the snapshot date.
    """

    timestamp: datetime
    total_value: float
    realised_pnl: float
    unrealised_pnl: float


@dataclass(frozen=True)
class TradeExtreme:
    """A single closed round-trip trade: its ticker, realized P&L, and exact fills.

    ``entry_at``/``exit_at`` are the paired buy/sell fill timestamps and
    ``entry_price``/``exit_price`` their fill prices; ``quantity`` is the closed size.
    """

    ticker: str
    realised_pnl: float
    quantity: float
    entry_price: float
    entry_at: datetime
    exit_price: float
    exit_at: datetime


@dataclass(frozen=True)
class BotKpis:
    """Performance figures for a bot session, from its own ledger + snapshots."""

    current_value: float
    #: Available (free, uninvested) cash — the balance not deployed in open positions.
    cash: float
    allocated_capital: float
    total_return: float
    total_return_pct: float
    realised_pnl: float
    unrealised_pnl: float
    total_fees: float
    total_trades: int
    max_drawdown: float
    #: Annualised Sharpe from the session's daily snapshot series; ``None`` until
    #: there are enough daily observations (mirrors the paper-trading contract).
    sharpe_ratio: float | None
    #: Best and worst closed round-trip by realized P&L; ``None`` until a position
    #: has been closed (no completed exit yet).
    best_trade: TradeExtreme | None
    worst_trade: TradeExtreme | None
    #: The session's benchmark id, its since-inception buy-and-hold return fraction,
    #: and the session's excess return fraction (total return minus the benchmark's).
    #: The two fractions are ``None`` until the session has a snapshot and the benchmark
    #: has usable stored closes.
    benchmark: str
    benchmark_return_pct: float | None
    excess_return_pct: float | None
    #: End-of-day value: the session's latest daily snapshot total value, or ``None``
    #: until a snapshot exists. Distinct from ``current_value``, which tracks the
    #: freshest observation (an intraday value point when newer than the snapshot).
    eod_value: float | None
    #: When the current value was captured (an intraday value point's ``captured_at``
    #: or a daily snapshot's ``created_at``), or ``None`` before any observation.
    value_as_of: datetime | None
    #: True when the current value came from an intraday value point rather than the
    #: daily snapshot.
    value_is_intraday: bool


@dataclass(frozen=True)
class SessionSummaryStats:
    """The curated stats block of a stopped session's summary.

    Assembled once a session is stopped from its own ledger + snapshots: the final
    figures (value, total return), the high-water mark and worst peak-to-trough drop,
    the lifespan and closed-trade record, the best/worst round-trip (with exact
    entry/exit), and the benchmark comparison. ``win_rate`` and the benchmark fractions
    are ``None`` when there is no closed trade / no usable benchmark data; ``stop_reason``
    and ``stopped_at`` are ``None`` for sessions stopped before stop metadata was recorded.
    """

    stop_reason: str | None
    stopped_at: datetime | None
    started_at: datetime
    lifespan_days: int
    final_value: float
    allocated_capital: float
    total_return: float
    total_return_pct: float
    realised_pnl: float
    peak_value: float
    max_drawdown: float
    trade_count: int
    win_rate: float | None
    best_trade: TradeExtreme | None
    worst_trade: TradeExtreme | None
    benchmark: str
    benchmark_return_pct: float | None
    excess_return_pct: float | None


@dataclass(frozen=True)
class BotSessionSummary:
    """A stopped session's summary: its stats block plus the cached AI narrative.

    ``narrative`` is ``None`` when it has not been generated yet or the agent failed
    on this view (the stats still render); ``model``/``generated_at`` describe the
    cached narrative when present.
    """

    stats: SessionSummaryStats
    narrative: str | None
    model: str | None
    generated_at: datetime | None


@dataclass(frozen=True)
class ValueObservation:
    """The most recently captured marked-to-market value of a session.

    Either the latest per-tick ``bot_value_points`` row or the latest daily
    ``bot_value_snapshots`` row — whichever was captured more recently.
    """

    total_value: float
    realised_pnl: float
    unrealised_pnl: float
    #: When the observation was captured, normalised to UTC.
    as_of: datetime
    #: True when the observation came from an intraday value point.
    is_intraday: bool


def _trade_symbol(asset: Asset) -> str:
    """The broker/market-data symbol for an asset (Alpaca form when known)."""
    return asset.alpaca_symbol or asset.ticker


def _traded_set_label(bot: BotSession) -> str:
    """A short label for a session's traded set: the ticker if one, else a count."""
    if len(bot.symbols) == 1:
        return bot.symbols[0].ticker
    return f"{len(bot.symbols)} symbols"


def bot_display_name(bot: BotSession) -> str:
    """The name a bot is shown under everywhere (lists, detail, dashboard, pushes).

    The explicit label when set; otherwise the display name of the preset it started
    from (or, without a preset, the strategy's display name), then `` · `` and its
    traded set. Internal strategy keys are never used as a name.
    """
    if bot.label:
        return bot.label
    name: str | None = None
    if bot.preset_key:
        try:
            name = presets.get_preset(bot.preset_key).display_name
        except UnknownPresetError:
            name = None
    if name is None:
        name = registry.get_strategy(bot.strategy_key).display_name
    return f"{name} · {_traded_set_label(bot)}"


# Lifecycle ---------------------------------------------------------------
def _resolve_equity_asset(session: Session, ticker: str) -> Asset:
    """Resolve an eligible equity in the universe by ticker, or reject it."""
    normalized = assets_service.normalize_ticker(ticker)
    matches = assets_service.list_assets(
        session, search=normalized, membership=AssetMembership.UNIVERSE
    )
    asset = next((a for a in matches if a.ticker == normalized), None)
    if (
        asset is None
        or not asset.is_eligible
        or asset.category != AssetCategory.STOCK.value
    ):
        raise IneligibleAssetError(
            f"{ticker!r} is not an eligible equity in the universe"
        )
    return asset


def resolve_universe_equities(session: Session) -> list[Asset]:
    """Every currently eligible universe equity (the whole-universe traded set)."""
    assets = assets_service.list_assets(
        session,
        membership=AssetMembership.UNIVERSE,
        categories=[AssetCategory.STOCK.value],
        limit=None,
    )
    return [asset for asset in assets if asset.is_eligible]


def create_bot_session(
    session: Session,
    *,
    strategy_key: str | None = None,
    initial_capital: float,
    benchmark: str,
    tickers: list[str] | None = None,
    whole_universe: bool = False,
    strategy_params: dict[str, object] | None | Literal[_Unset.TOKEN] = UNSET,
    label: str | None = None,
    take_profit_pct: float | None | Literal[_Unset.TOKEN] = UNSET,
    stop_loss_pct: float | None | Literal[_Unset.TOKEN] = UNSET,
    drawdown_stop_pct: float | None | Literal[_Unset.TOKEN] = UNSET,
    preset_key: str | None = None,
    cash_buffer_pct: float | None = None,
    sizing_method: str | None = None,
    risk_pct: float | None = None,
    atr_period: int | None = None,
    atr_k: float | None = None,
    max_position_pct: float | None = None,
    max_positions: int | None = None,
    origin: BotOrigin = BotOrigin.MANUAL,
    orchestrator_id: uuid.UUID | None = None,
) -> BotSession:
    """Create and persist an active multi-asset bot session, validating every input.

    ``origin`` / ``orchestrator_id`` record who created the session: the client API
    always creates ``MANUAL`` sessions; a bot orchestrator passes ``ORCHESTRATOR`` and
    its own id.

    The traded set is either the given ``tickers`` (each validated as an eligible
    universe equity) or, when ``whole_universe`` is set, the currently eligible universe
    equities resolved at creation. ``initial_capital`` becomes the session's shared cash
    pool and hard budget. Raises ``UnknownStrategyError`` for an unregistered strategy,
    ``InvalidStrategyParamsError`` for bad params, ``InvalidBotBenchmarkError`` for an
    unknown benchmark, ``IneligibleAssetError`` for a non-eligible / non-equity asset,
    and ``InvalidBotConfigError`` for an empty set or an unknown sizing method. No AI
    model is invoked.

    With ``preset_key`` the session starts from that preset: its strategy applies (a
    supplied ``strategy_key`` must match it), and each of ``strategy_params`` /
    ``take_profit_pct`` / ``stop_loss_pct`` / ``drawdown_stop_pct`` left as ``UNSET``
    takes the preset's value, while a supplied value (including ``None``) overrides it.
    The session records the preset and whether its effective configuration differs
    from it. Raises ``UnknownPresetError`` for an unknown preset and
    ``InvalidBotConfigError`` for a strategy mismatch or when neither a strategy nor a
    preset is given. Without a preset, ``UNSET`` behaves exactly like ``None``.
    """
    preset = presets.get_preset(preset_key) if preset_key is not None else None
    if preset is not None:
        if strategy_key is not None and strategy_key != preset.strategy_key.value:
            raise InvalidBotConfigError(
                f"strategy {strategy_key!r} does not match preset {preset.key!r} "
                f"(strategy {preset.strategy_key.value!r})"
            )
        strategy_key = preset.strategy_key.value
        if strategy_params is UNSET:
            strategy_params = dict(preset.strategy_params)
        if take_profit_pct is UNSET:
            take_profit_pct = preset.take_profit_pct
        if stop_loss_pct is UNSET:
            stop_loss_pct = preset.stop_loss_pct
        if drawdown_stop_pct is UNSET:
            drawdown_stop_pct = preset.drawdown_stop_pct
    if strategy_key is None:
        raise InvalidBotConfigError("a strategy key or a preset key is required")
    if strategy_params is UNSET:
        strategy_params = None
    if take_profit_pct is UNSET:
        take_profit_pct = None
    if stop_loss_pct is UNSET:
        stop_loss_pct = None
    if drawdown_stop_pct is UNSET:
        drawdown_stop_pct = None

    registration = registry.get_strategy(strategy_key)
    params = registration.parse_params(strategy_params or {})

    try:
        benchmark_enum = Benchmark(benchmark)
    except ValueError as exc:
        raise InvalidBotBenchmarkError(
            f"{benchmark!r} is not a known benchmark"
        ) from exc

    method_value = sizing_method or settings.BOT_SIZING_METHOD
    try:
        method = SizingMethod(method_value)
    except ValueError as exc:
        raise InvalidBotConfigError(
            f"{method_value!r} is not a known sizing method"
        ) from exc

    # Resolve the traded set (deduped, deterministic by ticker).
    if whole_universe:
        assets = resolve_universe_equities(session)
        if not assets:
            raise InvalidBotConfigError(
                "the eligible universe has no equities to trade"
            )
    else:
        if not tickers:
            raise InvalidBotConfigError("at least one ticker is required")
        resolved: dict[str, Asset] = {}
        for ticker in tickers:
            asset = _resolve_equity_asset(session, ticker)
            resolved[asset.ticker] = asset
        assets = list(resolved.values())
    assets.sort(key=lambda a: a.ticker)

    drawdown = (
        drawdown_stop_pct
        if drawdown_stop_pct is not None
        else settings.BOT_DRAWDOWN_STOP_PCT
    )
    buffer = (
        cash_buffer_pct
        if cash_buffer_pct is not None
        else settings.BOT_CASH_BUFFER_PCT
    )

    bot = BotSession(
        strategy_key=registration.key.value,
        label=label,
        status=BotSessionStatus.ACTIVE.value,
        benchmark=benchmark_enum.value,
        initial_capital=initial_capital,
        allocated_capital=initial_capital,
        cash=initial_capital,
        sizing_method=method.value,
        risk_pct=risk_pct if risk_pct is not None else settings.BOT_RISK_PCT,
        atr_period=(
            atr_period if atr_period is not None else settings.BOT_ATR_PERIOD
        ),
        atr_k=atr_k if atr_k is not None else settings.BOT_ATR_K,
        max_position_pct=(
            max_position_pct
            if max_position_pct is not None
            else settings.BOT_MAX_POSITION_PCT
        ),
        max_positions=(
            max_positions
            if max_positions is not None
            else settings.BOT_MAX_POSITIONS
        ),
        strategy_params=params.model_dump(),
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        drawdown_stop_pct=drawdown,
        cash_buffer_pct=buffer,
        peak_value=initial_capital,
        preset_key=preset.key if preset is not None else None,
        preset_customized=(
            preset is not None
            and _differs_from_preset(
                registration.parse_params(preset.strategy_params),
                preset,
                params=params,
                take_profit_pct=take_profit_pct,
                stop_loss_pct=stop_loss_pct,
                drawdown_stop_pct=drawdown,
            )
        ),
        origin=origin.value,
        orchestrator_id=orchestrator_id,
    )
    bot.symbols = [
        BotSymbol(
            asset_id=asset.id,
            ticker=asset.ticker,
            alpaca_symbol=_trade_symbol(asset),
        )
        for asset in assets
    ]
    session.add(bot)
    session.flush()
    return bot


def _same_risk(a: float | None, b: float | None) -> bool:
    """Whether two optional risk fractions are equal (``None`` = off)."""
    if a is None or b is None:
        return a is b
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def _differs_from_preset(
    preset_params: StrategyParams,
    preset: BotPreset,
    *,
    params: StrategyParams,
    take_profit_pct: float | None,
    stop_loss_pct: float | None,
    drawdown_stop_pct: float,
) -> bool:
    """Whether the effective configuration was customized away from ``preset``.

    Compares schema-normalized params (so omitted fields that default to the preset's
    values, e.g. inactive Donchian-version fields, compare equal) and the three risk
    controls with a float tolerance.
    """
    if params.model_dump() != preset_params.model_dump():
        return True
    return not (
        _same_risk(take_profit_pct, preset.take_profit_pct)
        and _same_risk(stop_loss_pct, preset.stop_loss_pct)
        and _same_risk(drawdown_stop_pct, preset.drawdown_stop_pct)
    )


def get_bot_session(session: Session, bot_id: uuid.UUID) -> BotSession:
    """Load a bot session by id, or raise ``BotSessionNotFoundError``."""
    bot = session.get(BotSession, bot_id)
    if bot is None:
        raise BotSessionNotFoundError(str(bot_id))
    return bot


def list_bot_sessions(
    session: Session, *, include_archived: bool = False
) -> list[BotSession]:
    """List bot sessions newest-first, hiding archived ones by default."""
    stmt = select(BotSession).order_by(BotSession.created_at.desc())
    if not include_archived:
        stmt = stmt.where(
            BotSession.status != BotSessionStatus.ARCHIVED.value
        )
    return list(session.execute(stmt).scalars())


def active_bot_sessions(session: Session) -> list[BotSession]:
    """Every active bot session (the tick/snapshot working set)."""
    stmt = (
        select(BotSession)
        .where(BotSession.status == BotSessionStatus.ACTIVE.value)
        .order_by(BotSession.created_at)
    )
    return list(session.execute(stmt).scalars())


def stop_bot_session(
    session: Session,
    bot_id: uuid.UUID,
    *,
    reason: StopReason = StopReason.MANUAL,
) -> BotSession:
    """Stop an active session (idempotent), recording ``reason`` and the stop time.

    Stopping never trades directly: the session stops evaluating entries at once, and
    any positions it still holds are sold by the next intraday tick while the market is
    open (see :func:`run_tick`'s flatten pass), so a stopped session ends up flat.
    """
    bot = get_bot_session(session, bot_id)
    if bot.status == BotSessionStatus.ACTIVE.value:
        bot.status = BotSessionStatus.STOPPED.value
        bot.stop_reason = reason.value
        bot.stopped_at = datetime.now(UTC)
    session.flush()
    return bot


def sessions_to_flatten(session: Session) -> list[BotSession]:
    """Non-active (stopped or archived) sessions that still hold open positions."""
    stmt = (
        select(BotSession)
        .where(BotSession.status != BotSessionStatus.ACTIVE.value)
        .where(BotSession.positions.any())
        .order_by(BotSession.created_at)
    )
    return list(session.execute(stmt).scalars())


def archive_bot_session(session: Session, bot_id: uuid.UUID) -> BotSession:
    """Archive a stopped session, or raise if it is not stopped."""
    bot = get_bot_session(session, bot_id)
    if bot.status == BotSessionStatus.ARCHIVED.value:
        return bot
    if bot.status != BotSessionStatus.STOPPED.value:
        raise BotSessionNotArchivableError(
            "only a stopped session can be archived"
        )
    bot.status = BotSessionStatus.ARCHIVED.value
    bot.archived_at = datetime.now(UTC)
    session.flush()
    return bot


# Tick runner -------------------------------------------------------------
def _fetch_session_bars(
    bot: BotSession,
    market_data: MarketData,
    *,
    history: int,
    timeframe: str,
    now: datetime,
) -> dict[str, list[Bar]]:
    """Fetch fresh bars for each traded symbol, keyed by ticker (stale symbols omitted)."""
    bars_by_ticker: dict[str, list[Bar]] = {}
    for symbol in bot.symbols:
        result = market_data.latest_bars(
            symbol.alpaca_symbol, timeframe, history, now=now
        )
        if result.fresh and result.bars:
            bars_by_ticker[symbol.ticker] = result.bars
    return bars_by_ticker


def _record_value_point(
    session: Session,
    bot: BotSession,
    marks: dict[str, float],
    *,
    captured_at: datetime,
) -> None:
    """Persist an intraday value point for ``bot`` at ``captured_at``.

    Records the session's total value (cash plus positions marked at ``marks``, or
    average cost where a mark is absent) and its realised/unrealised P&L — the same
    basis as the daily snapshot, at tick granularity. Additive to the trading path:
    it reads already-updated state and does not alter positions, cash, or the ledger.
    """
    session.add(
        BotValuePoint(
            session=bot,
            captured_at=captured_at,
            total_value=total_value(bot, marks),
            realised_pnl=bot.realised_pnl,
            unrealised_pnl=unrealised_pnl(bot, marks),
        )
    )


def _tick_session(
    bot: BotSession,
    *,
    session: Session,
    engine: ExecutionEngine,
    market_data: MarketData,
    tick_now: datetime,
    notifier: Notifier | None = None,
) -> bool:
    """Advance one active session; return whether it was processed (not fully skipped).

    Stateless recompute: fetch each symbol's bars, then process the drawdown kill-switch,
    then per-position exits (take-profit / stop-loss / EXIT signal), then deterministic
    budget-bounded entries. A symbol with stale/missing fresh data is skipped this tick;
    if no symbol has fresh data the whole session is skipped.
    """
    registration = registry.get_strategy(bot.strategy_key)
    params = registration.parse_params(bot.strategy_params)
    history = max(params.required_history, bot.atr_period + 1)
    timeframe = settings.BOT_SIGNAL_BAR_TIMEFRAME

    bars_by_ticker = _fetch_session_bars(
        bot, market_data, history=history, timeframe=timeframe, now=tick_now
    )
    if not bars_by_ticker:
        return False

    # Marks for valuation: the fresh close where available, else the position's
    # average cost (a neutral mark for a symbol with no fresh bar this tick).
    marks = {ticker: bars[-1].close for ticker, bars in bars_by_ticker.items()}
    bot.peak_value = max(bot.peak_value, total_value(bot, marks))

    # 1. Whole-session drawdown kill-switch — exit everything and stop.
    if total_value(bot, marks) <= bot.peak_value * (1.0 - bot.drawdown_stop_pct):
        liquidated = [position.ticker for position in bot.positions]
        realised_before = bot.realised_pnl
        for position in list(bot.positions):
            engine.exit(bot, position, now=tick_now, reason=REASON_DRAWDOWN)
        bot.status = BotSessionStatus.STOPPED.value
        bot.stop_reason = StopReason.DRAWDOWN_KILL_SWITCH.value
        bot.stopped_at = tick_now
        bot.last_tick_at = tick_now
        _record_value_point(session, bot, marks, captured_at=tick_now)
        _notify_safely(
            notifier,
            title=f"Cadence bot: {bot_display_name(bot)} drawdown kill-switch",
            message=_kill_switch_message(
                liquidated, bot.realised_pnl - realised_before
            ),
        )
        return True

    # 2. Exits before entries — per open position, in deterministic ticker order.
    for position in sorted(bot.positions, key=lambda p: p.ticker):
        bars = bars_by_ticker.get(position.ticker)
        if bars is None:  # stale this tick: leave the position untouched.
            continue
        price = bars[-1].close
        risk_reason = take_profit_stop_loss_reason(
            avg_price=position.avg_price,
            price=price,
            take_profit_pct=bot.take_profit_pct,
            stop_loss_pct=bot.stop_loss_pct,
        )
        if risk_reason is not None:
            engine.exit(bot, position, now=tick_now, reason=risk_reason)
            continue
        signal = registration.strategy.evaluate(
            bars,
            PositionView(quantity=position.quantity, avg_price=position.avg_price),
            params,
        )
        if signal.action is SignalAction.EXIT:
            engine.exit(bot, position, now=tick_now, reason=signal.reason)

    # 3. Entries — deterministic ascending-ticker order, budget- and slot-bounded.
    method = SizingMethod(bot.sizing_method)
    open_tickers = {p.ticker for p in bot.positions}
    candidates: list[EntryCandidate] = []
    reasons: dict[str, str] = {}
    for symbol in bot.symbols:
        if symbol.ticker in open_tickers:
            continue
        bars = bars_by_ticker.get(symbol.ticker)
        if bars is None:
            continue
        signal = registration.strategy.evaluate(bars, None, params)
        if signal.action is not SignalAction.ENTER_LONG:
            continue
        atr_value = (
            atr(bars, bot.atr_period)
            if method is SizingMethod.ATR_RISK
            else None
        )
        candidates.append(
            EntryCandidate(
                ticker=symbol.ticker,
                symbol=symbol.alpaca_symbol,
                asset_id=symbol.asset_id,
                price=bars[-1].close,
                atr_value=atr_value,
            )
        )
        reasons[symbol.ticker] = signal.reason
    candidates.sort(key=lambda c: c.ticker)

    planned = plan_entries(
        candidates,
        budget=bot.initial_capital,
        available_cash=bot.cash,
        open_positions=len(bot.positions),
        max_positions=bot.max_positions,
        sizing_method=method,
        risk_pct=bot.risk_pct,
        atr_k=bot.atr_k,
        max_position_pct=bot.max_position_pct,
        cash_buffer_pct=bot.cash_buffer_pct,
    )
    for entry in planned:
        engine.enter(
            bot,
            asset_id=entry.candidate.asset_id,
            ticker=entry.candidate.ticker,
            symbol=entry.candidate.symbol,
            shares=entry.shares,
            price=entry.candidate.price,
            now=tick_now,
            reason=reasons[entry.candidate.ticker],
        )

    bot.last_tick_at = tick_now
    _record_value_point(session, bot, marks, captured_at=tick_now)
    return True


def run_tick(
    session: Session,
    *,
    broker: Broker,
    market_data: MarketData,
    now: datetime | None = None,
    notifier: Notifier | None = None,
) -> TickResult:
    """Flatten stopped sessions, then advance every active bot session once.

    No-op when the equity market is closed. First, every stopped or archived session
    that still holds positions has them sold at market (a stopped session must end up
    flat). Then, for each active session it fetches each
    traded symbol's required bar history from ``market_data`` at the configured
    timeframe, processes exits before entries, and sizes entries from the shared cash
    pool. A session with no fresh symbol data is counted as skipped. When a session's
    drawdown kill-switch trips, a best-effort notification is sent via ``notifier``
    (a ``None`` notifier stays silent and a notifier failure never fails the tick).

    Unrecorded bot orders from earlier ticks are reconciled first. Each session is then
    processed and committed on its own: a session that raises (including a broker
    rejection) is rolled back alone, counted as failed, and the tick carries on.
    """
    if not broker.is_market_open():
        return TickResult(market_open=False)

    tick_now = now or datetime.now(UTC)
    # Book any order an earlier tick sent but never recorded before deciding anything.
    reconciled = reconcile_orders(session, broker, owner_kind=OrderOwnerKind.BOT)
    engine = ExecutionEngine(session, broker)

    flattened = 0
    failed = 0
    for stopped in sessions_to_flatten(session):
        bot_id = stopped.id
        try:
            flattened += _flatten_session(stopped, engine=engine, tick_now=tick_now)
            _clear_failure(stopped)
            session.commit()
        except Exception as exc:  # one bot must not fail the tick
            session.rollback()
            failed += 1
            _logger.warning(
                "tick: flattening bot session %s failed", bot_id, exc_info=True
            )
            _record_failure(session, bot_id, exc, at=tick_now)

    processed = 0
    skipped = 0
    for bot in active_bot_sessions(session):
        bot_id = bot.id
        try:
            ticked = _tick_session(
                bot,
                session=session,
                engine=engine,
                market_data=market_data,
                tick_now=tick_now,
                notifier=notifier,
            )
            if ticked:
                _clear_failure(bot)
            session.commit()
        except Exception as exc:  # one bot must not fail the tick
            session.rollback()
            failed += 1
            _logger.warning("tick: bot session %s failed", bot_id, exc_info=True)
            _record_failure(session, bot_id, exc, at=tick_now)
            continue
        if ticked:
            processed += 1
        else:
            skipped += 1

    session.flush()
    return TickResult(
        market_open=True,
        processed=processed,
        skipped=skipped,
        flattened=flattened,
        failed=failed,
        reconciled=reconciled.booked,
    )


def _clear_failure(bot: BotSession) -> None:
    """Reset a session's tick failure state after it was processed successfully."""
    if bot.consecutive_failures or bot.last_failure_at is not None:
        bot.consecutive_failures = 0
        bot.last_failure_at = None
        bot.last_failure_error = None


def _record_failure(
    session: Session, bot_id: uuid.UUID, exc: Exception, *, at: datetime
) -> None:
    """Record that processing a session failed this tick (best-effort, own commit).

    Runs after the session's own work was rolled back; a failure to record is logged
    and never fails the tick.
    """
    try:
        bot = session.get(BotSession, bot_id)
        if bot is None:
            return
        bot.consecutive_failures = (bot.consecutive_failures or 0) + 1
        bot.last_failure_at = at
        bot.last_failure_error = (str(exc) or type(exc).__name__)[:_FAILURE_MESSAGE_MAX]
        session.commit()
    except Exception:  # the failure state is diagnostic only
        session.rollback()
        _logger.warning("tick: could not record the failure of %s", bot_id, exc_info=True)


def _flatten_session(
    stopped: BotSession, *, engine: ExecutionEngine, tick_now: datetime
) -> int:
    """Sell a stopped session's positions; return how many were sold.

    A rejected sell (e.g. the shared account no longer holds the shares) keeps the
    position and is retried on the next tick; a sell larger than the account's holding
    is refused by the order gateway before anything is sent.
    """
    sold = 0
    for position in list(stopped.positions):
        try:
            outcome = engine.exit(
                stopped, position, now=tick_now, reason=REASON_SESSION_STOPPED
            )
        except BrokerError:
            _logger.warning(
                "could not sell %s for stopped bot session %s; will retry",
                position.ticker,
                stopped.id,
                exc_info=True,
            )
            continue
        if outcome.action == "exit":
            sold += 1
    return sold


# Snapshots & KPIs --------------------------------------------------------
def _mark_positions(bot: BotSession, broker: Broker) -> dict[str, float]:
    """Latest mark prices for the session's open positions, keyed by ticker."""
    marks: dict[str, float] = {}
    for position in bot.positions:
        quote = broker.get_quote(position.alpaca_symbol, AssetClass.EQUITY)
        price = quote.last if quote.last is not None else quote.mid
        marks[position.ticker] = price if price is not None else position.avg_price
    return marks


def record_bot_snapshot(
    session: Session,
    bot: BotSession,
    *,
    marks: dict[str, float],
    snapshot_date: date | None = None,
) -> BotValueSnapshot:
    """Upsert the daily value snapshot for ``bot`` (one row per session per day).

    ``marks`` maps a held position's ticker to its mark price; a position absent from
    ``marks`` is marked at its average cost (zero unrealised contribution).
    """
    when = snapshot_date or datetime.now(UTC).date()
    value = total_value(bot, marks)
    unrealised = unrealised_pnl(bot, marks)

    bot.peak_value = max(bot.peak_value, value)

    existing = session.execute(
        select(BotValueSnapshot).where(
            BotValueSnapshot.bot_session_id == bot.id,
            BotValueSnapshot.snapshot_date == when,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.total_value = value
        existing.realised_pnl = bot.realised_pnl
        existing.unrealised_pnl = unrealised
        session.flush()
        return existing

    snapshot = BotValueSnapshot(
        session=bot,
        snapshot_date=when,
        total_value=value,
        realised_pnl=bot.realised_pnl,
        unrealised_pnl=unrealised,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def count_bot_trades_on(session: Session, bot: BotSession, day: date) -> int:
    """Number of trades the session executed on ``day`` (UTC calendar day).

    Counts ``BotTrade`` rows whose ``created_at`` falls within the UTC day, matching
    the basis on which the daily snapshot date is derived. Distinct from the lifetime
    ``total_trades`` the KPIs expose.
    """
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    stmt = (
        select(func.count())
        .select_from(BotTrade)
        .where(
            BotTrade.bot_session_id == bot.id,
            BotTrade.created_at >= start,
            BotTrade.created_at < end,
        )
    )
    return int(session.execute(stmt).scalar_one())


def get_previous_bot_value_snapshot(
    session: Session, *, session_id: uuid.UUID, before: date
) -> BotValueSnapshot | None:
    """The session's most recent value snapshot strictly before ``before``, if any."""
    stmt = (
        select(BotValueSnapshot)
        .where(
            BotValueSnapshot.bot_session_id == session_id,
            BotValueSnapshot.snapshot_date < before,
        )
        .order_by(BotValueSnapshot.snapshot_date.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def bot_daily_pnl(
    session: Session, bot: BotSession, snapshot: BotValueSnapshot
) -> tuple[float, float | None]:
    """Day-over-day P&L (amount, percent) for a session's snapshot.

    Diffs the snapshot's total value against the prior snapshot's (or, on day one, the
    session's allocated capital). The percent uses that baseline and is ``None`` when
    the baseline is non-positive, mirroring the AI daily report's guard.
    """
    prior = get_previous_bot_value_snapshot(
        session, session_id=bot.id, before=snapshot.snapshot_date
    )
    baseline = prior.total_value if prior is not None else bot.allocated_capital
    daily_pnl = snapshot.total_value - baseline
    daily_pnl_pct = daily_pnl / baseline if baseline > 0 else None
    return daily_pnl, daily_pnl_pct


def _bot_benchmark_returns(
    session: Session,
    bot: BotSession,
    snapshots: list[BotValueSnapshot],
    *,
    total_return_pct: float,
    as_of: date,
) -> tuple[float | None, float | None]:
    """The bot's since-inception benchmark return and excess return, as fractions.

    A simple since-inception buy-and-hold benchmark return (bots have no capital-
    increase events, so no time-weighting is needed) compared against the bot's own
    total return. Both are ``None`` when the session has no snapshots or the benchmark
    lacks usable stored closes for the period. Shared by the per-session KPIs and the
    daily-summary benchmark suffix so the two never diverge.
    """
    if not snapshots:
        return None, None
    series = load_benchmark_series(session, bot.benchmark)
    benchmark_return = benchmark_return_fraction(
        series, start_date=snapshots[0].snapshot_date, as_of=as_of
    )
    if benchmark_return is None:
        return None, None
    return benchmark_return, total_return_pct - benchmark_return


def _bot_benchmark_suffix(
    session: Session,
    bot: BotSession,
    snapshots: list[BotValueSnapshot],
    *,
    total_return_pct: float,
    as_of: date,
) -> str | None:
    """Benchmark comparison suffix for a bot's daily summary line, or ``None``.

    Formats the shared ``_bot_benchmark_returns`` figures. Returns ``None`` when the
    session has no snapshots or the benchmark lacks usable stored closes, so the caller
    omits the suffix.
    """
    benchmark_return, excess = _bot_benchmark_returns(
        session, bot, snapshots, total_return_pct=total_return_pct, as_of=as_of
    )
    if benchmark_return is None or excess is None:
        return None
    name = benchmark_display_name(Benchmark(bot.benchmark))
    return (
        f"vs {name}: {_signed_pct(benchmark_return)} "
        f"(excess {_signed_pct(excess)})"
    )


def run_bot_snapshots(
    session: Session,
    *,
    broker: Broker,
    now: datetime | None = None,
    notifier: Notifier | None = None,
) -> SnapshotResult:
    """Record a daily value snapshot for every active session.

    Unrecorded bot orders are reconciled first, so a fill that landed after the
    session's last tick (an order sent just before the close) is booked into its bot
    the same evening and the snapshot includes it. A reconciliation failure is logged
    and never prevents the snapshots.

    For each snapshotted session that was not deployed by a bot orchestrator it also
    sends one best-effort daily-summary push via ``notifier`` (orchestrator-deployed bots
    are rolled up into their orchestrator's daily push) mirroring the AI daily report —
    value and day-over-day change, total return, realised/unrealised P&L, cash, fees,
    Sharpe, a benchmark comparison, the best/worst open position, and the number of
    trades executed that day. A ``None`` notifier stays silent and a notifier failure
    never fails the snapshot job.
    """
    when = (now or datetime.now(UTC)).date()
    try:
        reconciled = reconcile_orders(
            session, broker, owner_kind=OrderOwnerKind.BOT, now=now
        ).booked
    except Exception:  # the snapshots must still run
        session.rollback()
        _logger.warning("snapshot: reconciling bot orders failed", exc_info=True)
        reconciled = 0
    count = 0
    for bot in active_bot_sessions(session):
        marks = _mark_positions(bot, broker)
        snapshot = record_bot_snapshot(
            session, bot, marks=marks, snapshot_date=when
        )
        count += 1
        if bot.orchestrator_id is not None:
            # Rolled up: the orchestrator's own daily push covers its bots.
            continue

        kpis = bot_session_kpis(session, bot)
        daily_pnl, daily_pnl_pct = bot_daily_pnl(session, bot, snapshot)
        benchmark_suffix = _bot_benchmark_suffix(
            session,
            bot,
            list_bot_snapshots(session, bot),
            total_return_pct=kpis.total_return_pct,
            as_of=when,
        )
        holdings = [
            (position.ticker, marks[position.ticker] / position.avg_price - 1.0)
            for position in bot.positions
            if position.avg_price > 0 and position.ticker in marks
        ]
        _notify_safely(
            notifier,
            title=f"Cadence bot: {bot_display_name(bot)} daily P&L",
            message=_bot_summary_message(
                kpis,
                daily_pnl=daily_pnl,
                daily_pnl_pct=daily_pnl_pct,
                cash=bot.cash,
                trades_today=count_bot_trades_on(session, bot, when),
                benchmark_suffix=benchmark_suffix,
                holdings=holdings,
            ),
        )
    _prune_value_points(session, now=now or datetime.now(UTC))
    _prune_tick_runs(session, now=now or datetime.now(UTC))
    session.flush()
    return SnapshotResult(snapshots=count, reconciled=reconciled)


def _prune_value_points(session: Session, *, now: datetime) -> None:
    """Delete intraday value points older than the retention window, all sessions.

    A single bulk delete bounds the ``bot_value_points`` table: the ``5min`` and
    ``hourly`` chart resolutions read these points, so they span roughly the
    retention window; ``daily``/``monthly`` come from daily snapshots and are
    unaffected. Called from the daily snapshot job.
    """
    cutoff = now - timedelta(days=settings.BOT_VALUE_POINT_RETENTION_DAYS)
    session.execute(
        delete(BotValuePoint).where(BotValuePoint.captured_at < cutoff)
    )


def _prune_tick_runs(session: Session, *, now: datetime) -> None:
    """Delete tick outcomes older than the tick-run retention window (daily job)."""
    cutoff = now - timedelta(days=settings.BOT_TICK_RUN_RETENTION_DAYS)
    session.execute(delete(BotTickRun).where(BotTickRun.ran_at < cutoff))


# Tick outcomes -------------------------------------------------------------
def record_tick_run(
    session: Session, *, ran_at: datetime, result: TickResult
) -> BotTickRun:
    """Record a completed tick's outcome in the caller's unit of work."""
    run = BotTickRun(
        ran_at=ran_at,
        market_open=result.market_open,
        processed=result.processed,
        skipped=result.skipped,
        failed=result.failed,
        flattened=result.flattened,
        reconciled=result.reconciled,
    )
    session.add(run)
    session.flush()
    return run


def record_failed_tick(*, ran_at: datetime, error: str, market_open: bool) -> None:
    """Record a tick that crashed, in its own committed session.

    The tick's request session is rolled back with the failure, so the outcome is written
    independently; a failure to record is logged and swallowed so it never masks the
    tick's own error.
    """
    try:
        with database.SessionLocal() as db:
            db.add(
                BotTickRun(
                    ran_at=ran_at,
                    market_open=market_open,
                    processed=0,
                    skipped=0,
                    failed=0,
                    flattened=0,
                    reconciled=0,
                    error=error[:_FAILURE_MESSAGE_MAX],
                )
            )
            db.commit()
    except Exception:  # never mask the tick's own failure
        _logger.warning("could not record the failed tick", exc_info=True)


def latest_tick_run(session: Session) -> BotTickRun | None:
    """The most recently recorded tick outcome, if any."""
    return session.execute(
        select(BotTickRun).order_by(BotTickRun.ran_at.desc()).limit(1)
    ).scalar_one_or_none()


def failing_bot_sessions(session: Session) -> list[BotSession]:
    """Non-archived sessions whose latest tick processing failed, most failures first."""
    stmt = (
        select(BotSession)
        .where(BotSession.consecutive_failures > 0)
        .where(BotSession.status != BotSessionStatus.ARCHIVED.value)
        .order_by(
            BotSession.consecutive_failures.desc(), BotSession.last_failure_at.desc()
        )
    )
    return list(session.execute(stmt).scalars())


def _max_drawdown(values: list[float]) -> float:
    """Largest peak-to-trough drop over ``values`` as a positive fraction."""
    peak = float("-inf")
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def list_bot_snapshots(
    session: Session, bot: BotSession
) -> list[BotValueSnapshot]:
    """Value snapshots for a session, oldest-first (the equity curve)."""
    stmt = (
        select(BotValueSnapshot)
        .where(BotValueSnapshot.bot_session_id == bot.id)
        .order_by(BotValueSnapshot.snapshot_date)
    )
    return list(session.execute(stmt).scalars())


def list_bot_trades_page(
    session: Session, bot: BotSession, *, limit: int, offset: int
) -> tuple[list[BotTrade], int]:
    """A single page of a session's trade ledger plus the full trade count.

    Returns ``(items, total)`` where ``items`` is the requested window ordered
    most-recent-first (ties broken by ``id`` for a stable order across pages) and
    ``total`` is the session's full trade count. Serves one page without loading the
    whole ``trades`` relationship into memory.
    """
    total = int(
        session.execute(
            select(func.count())
            .select_from(BotTrade)
            .where(BotTrade.bot_session_id == bot.id)
        ).scalar_one()
    )
    stmt = (
        select(BotTrade)
        .where(BotTrade.bot_session_id == bot.id)
        .order_by(BotTrade.created_at.desc(), BotTrade.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars()), total


#: End-of-day clock time stamped onto daily/monthly value-history points so an
#: intraday and a daily series share one timeline (a day's point sorts after its
#: own intraday points).
_END_OF_DAY = time(23, 59, 59)


def _point_from_snapshot(snapshot: BotValueSnapshot) -> BotValueHistoryPoint:
    """Map a daily snapshot to an end-of-day timestamped history point."""
    return BotValueHistoryPoint(
        timestamp=datetime.combine(snapshot.snapshot_date, _END_OF_DAY, tzinfo=UTC),
        total_value=snapshot.total_value,
        realised_pnl=snapshot.realised_pnl,
        unrealised_pnl=snapshot.unrealised_pnl,
    )


def list_bot_value_history(
    session: Session, bot: BotSession, *, resolution: BotValueResolution
) -> list[BotValueHistoryPoint]:
    """A session's value history at ``resolution``, oldest-first (empty when no data).

    - ``5min``: raw ``bot_value_points`` (one per processed tick).
    - ``hourly``: the last intraday point in each clock hour.
    - ``daily``: the daily ``bot_value_snapshots`` equity curve.
    - ``monthly``: the last daily snapshot in each calendar month.

    Intraday resolutions read the retention-bounded ``bot_value_points`` table, so they
    span roughly the retention window; daily/monthly read the unbounded snapshot series.
    Downsampling is deterministic: grouping keys are derived from the timestamp and the
    last point per group wins.
    """
    if resolution in (BotValueResolution.FIVE_MIN, BotValueResolution.HOURLY):
        points = list(
            session.execute(
                select(BotValuePoint)
                .where(BotValuePoint.bot_session_id == bot.id)
                .order_by(BotValuePoint.captured_at, BotValuePoint.id)
            ).scalars()
        )
        if resolution is BotValueResolution.FIVE_MIN:
            return [
                BotValueHistoryPoint(
                    timestamp=p.captured_at,
                    total_value=p.total_value,
                    realised_pnl=p.realised_pnl,
                    unrealised_pnl=p.unrealised_pnl,
                )
                for p in points
            ]
        # Hourly: last point per clock hour, preserving chronological order.
        by_hour: dict[datetime, BotValuePoint] = {}
        for p in points:
            by_hour[p.captured_at.replace(minute=0, second=0, microsecond=0)] = p
        return [
            BotValueHistoryPoint(
                timestamp=p.captured_at,
                total_value=p.total_value,
                realised_pnl=p.realised_pnl,
                unrealised_pnl=p.unrealised_pnl,
            )
            for p in by_hour.values()
        ]

    snapshots = list_bot_snapshots(session, bot)
    if resolution is BotValueResolution.DAILY:
        return [_point_from_snapshot(s) for s in snapshots]
    # Monthly: last daily snapshot per calendar month, preserving order.
    by_month: dict[tuple[int, int], BotValueSnapshot] = {}
    for s in snapshots:
        by_month[(s.snapshot_date.year, s.snapshot_date.month)] = s
    return [_point_from_snapshot(s) for s in by_month.values()]


def _bot_sharpe(snapshots: list[BotValueSnapshot]) -> float | None:
    """Annualised Sharpe from a session's daily value-snapshot series, or ``None``.

    Builds the daily fractional-return series from consecutive ``total_value`` diffs
    (bots have no mid-life capital-increase events, so total-value diffs are clean
    returns) and reuses the paper-trading Sharpe helper, which returns ``None`` until
    there are enough observations or when the series is flat.
    """
    returns = [
        curr.total_value / prev.total_value - 1.0
        for prev, curr in pairwise(snapshots)
        if prev.total_value > 0
    ]
    daily_risk_free = settings.SHARPE_RISK_FREE_RATE / SHARPE_TRADING_DAYS_PER_YEAR
    return paper_service.sharpe_ratio(returns, risk_free=daily_risk_free)


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive timestamp as UTC so value observations compare safely."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def latest_value_observation(
    session: Session, bot: BotSession
) -> ValueObservation | None:
    """The session's most recently captured value observation, or ``None``.

    Compares the latest intraday ``bot_value_points`` row (by ``captured_at``) with the
    latest daily ``bot_value_snapshots`` row (by ``created_at``) and returns whichever was
    captured more recently — already marked-to-market at capture, so it carries a
    consistent ``total_value``/``unrealised_pnl`` pair. The intraday point wins an
    exact-timestamp tie. Returns ``None`` when the session has neither, making no live
    broker or quote call. Shared by the per-session current value and KPIs.
    """
    latest_point = session.execute(
        select(BotValuePoint)
        .where(BotValuePoint.bot_session_id == bot.id)
        .order_by(BotValuePoint.captured_at.desc(), BotValuePoint.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    snapshots = list_bot_snapshots(session, bot)
    latest_snapshot = snapshots[-1] if snapshots else None

    point_obs = (
        ValueObservation(
            total_value=latest_point.total_value,
            realised_pnl=latest_point.realised_pnl,
            unrealised_pnl=latest_point.unrealised_pnl,
            as_of=_as_utc(latest_point.captured_at),
            is_intraday=True,
        )
        if latest_point is not None
        else None
    )
    snapshot_obs = (
        ValueObservation(
            total_value=latest_snapshot.total_value,
            realised_pnl=latest_snapshot.realised_pnl,
            unrealised_pnl=latest_snapshot.unrealised_pnl,
            as_of=_as_utc(latest_snapshot.created_at),
            is_intraday=False,
        )
        if latest_snapshot is not None
        else None
    )
    if point_obs is None:
        return snapshot_obs
    if snapshot_obs is None:
        return point_obs
    # Both exist: the more recent wins; the intraday point wins an exact tie.
    return point_obs if point_obs.as_of >= snapshot_obs.as_of else snapshot_obs


def bot_current_value(session: Session, bot: BotSession) -> float:
    """A session's live value: cash plus its marked-to-market open positions.

    Returns the most recently captured value observation (the latest intraday value
    point when newer than the latest daily snapshot, otherwise the latest snapshot —
    both marked-to-market at capture); before any observation exists it falls back to
    cash plus open positions valued at cost. This is the single source of truth for a
    session's live value, shared by the per-session KPIs and the session list.
    """
    observation = latest_value_observation(session, bot)
    if observation is not None:
        return observation.total_value
    # No snapshot or value point yet: cash plus positions marked at cost.
    return total_value(bot, {})


def bot_eod_value(session: Session, bot: BotSession) -> float | None:
    """A session's end-of-day value: its latest daily snapshot total value, or ``None``.

    Always the latest daily ``bot_value_snapshots`` row (independent of any newer
    intraday value point), so it is the last end-of-day close rather than the live mark.
    ``None`` until the session has recorded at least one snapshot.
    """
    snapshots = list_bot_snapshots(session, bot)
    return snapshots[-1].total_value if snapshots else None


def bot_round_trips(session: Session, bot: BotSession) -> list[TradeExtreme]:
    """Every closed round-trip for a session, oldest exit first.

    Walks the ledger oldest-first, pairing each sell (a full exit) with its ticker's
    open entry basis; a round-trip's realized P&L is the exit proceeds minus the entry
    cost, net of both fills' fees. Relies on the one-position-per-symbol + full-exit
    invariants, so each ticker's fills strictly alternate buy → sell. Shared by the
    best/worst-trade and summary (trade count, win rate) readers.
    """
    stmt = (
        select(BotTrade)
        .where(BotTrade.bot_session_id == bot.id)
        .order_by(BotTrade.created_at, BotTrade.id)
    )
    # ticker -> (entry price, entry quantity, entry fees, entry time) for its open position.
    open_basis: dict[str, tuple[float, float, float, datetime]] = {}
    round_trips: list[TradeExtreme] = []
    for trade in session.execute(stmt).scalars():
        if trade.filled_price is None:
            continue
        if trade.side == OrderSide.BUY.value:
            open_basis[trade.ticker] = (
                trade.filled_price,
                trade.quantity,
                trade.fees,
                trade.created_at,
            )
        else:  # sell — closes this ticker's open position
            entry = open_basis.pop(trade.ticker, None)
            if entry is None:
                continue
            entry_price, _entry_qty, entry_fees, entry_at = entry
            pnl = (
                (trade.filled_price - entry_price) * trade.quantity
                - entry_fees
                - trade.fees
            )
            round_trips.append(
                TradeExtreme(
                    ticker=trade.ticker,
                    realised_pnl=pnl,
                    quantity=trade.quantity,
                    entry_price=entry_price,
                    entry_at=entry_at,
                    exit_price=trade.filled_price,
                    exit_at=trade.created_at,
                )
            )
    return round_trips


def bot_trade_extremes(
    session: Session, bot: BotSession
) -> tuple[TradeExtreme | None, TradeExtreme | None]:
    """The session's best and worst closed round-trip by realized P&L.

    Returns ``(best, worst)`` — the max- and min-P&L round-trips — or ``(None, None)``
    when no position has been closed yet.
    """
    round_trips = bot_round_trips(session, bot)
    if not round_trips:
        return None, None
    best = max(round_trips, key=lambda t: t.realised_pnl)
    worst = min(round_trips, key=lambda t: t.realised_pnl)
    return best, worst


def bot_session_kpis(session: Session, bot: BotSession) -> BotKpis:
    """Compute KPIs for a session from its own ledger and value snapshots."""
    snapshots = list_bot_snapshots(session, bot)
    observation = latest_value_observation(session, bot)
    if observation is not None:
        current_value = observation.total_value
        unrealised = observation.unrealised_pnl
        value_as_of: datetime | None = observation.as_of
        value_is_intraday = observation.is_intraday
    else:
        # No snapshot or value point yet: cash plus positions marked at cost.
        current_value = total_value(bot, {})
        unrealised = 0.0
        value_as_of = None
        value_is_intraday = False

    total_return = current_value - bot.allocated_capital
    total_return_pct = (
        total_return / bot.allocated_capital
        if bot.allocated_capital
        else 0.0
    )
    best_trade, worst_trade = bot_trade_extremes(session, bot)
    benchmark_return_pct, excess_return_pct = _bot_benchmark_returns(
        session,
        bot,
        snapshots,
        total_return_pct=total_return_pct,
        as_of=datetime.now(UTC).date(),
    )
    return BotKpis(
        current_value=current_value,
        cash=bot.cash,
        allocated_capital=bot.allocated_capital,
        total_return=total_return,
        total_return_pct=total_return_pct,
        realised_pnl=bot.realised_pnl,
        unrealised_pnl=unrealised,
        total_fees=bot.total_fees,
        total_trades=bot.total_trades,
        max_drawdown=_max_drawdown([s.total_value for s in snapshots]),
        sharpe_ratio=_bot_sharpe(snapshots),
        best_trade=best_trade,
        worst_trade=worst_trade,
        benchmark=bot.benchmark,
        benchmark_return_pct=benchmark_return_pct,
        excess_return_pct=excess_return_pct,
        eod_value=snapshots[-1].total_value if snapshots else None,
        value_as_of=value_as_of,
        value_is_intraday=value_is_intraday,
    )


def bot_session_summary_stats(
    session: Session, bot: BotSession
) -> SessionSummaryStats:
    """Assemble the curated stats block for a (typically stopped) session.

    Reuses the KPI reader for final value / total return / best-worst / benchmark,
    the persisted ``peak_value`` high-water mark, the snapshot-series max drawdown, and
    the full closed-round-trip walk for trade count and win rate. Lifespan is whole days
    from the session start to its stop time (or now when not yet stopped). Tolerant of
    missing stop metadata: ``stop_reason``/``stopped_at`` pass through as ``None``.
    """
    kpis = bot_session_kpis(session, bot)
    round_trips = bot_round_trips(session, bot)
    trade_count = len(round_trips)
    win_rate: float | None = (
        sum(1 for t in round_trips if t.realised_pnl > 0) / trade_count
        if trade_count
        else None
    )
    started_at = _as_utc(bot.created_at)
    end = bot.stopped_at or datetime.now(UTC)
    lifespan_days = max((_as_utc(end).date() - started_at.date()).days, 0)
    return SessionSummaryStats(
        stop_reason=bot.stop_reason,
        stopped_at=bot.stopped_at,
        started_at=started_at,
        lifespan_days=lifespan_days,
        final_value=kpis.current_value,
        allocated_capital=kpis.allocated_capital,
        total_return=kpis.total_return,
        total_return_pct=kpis.total_return_pct,
        realised_pnl=kpis.realised_pnl,
        peak_value=bot.peak_value,
        max_drawdown=kpis.max_drawdown,
        trade_count=trade_count,
        win_rate=win_rate,
        best_trade=kpis.best_trade,
        worst_trade=kpis.worst_trade,
        benchmark=kpis.benchmark,
        benchmark_return_pct=kpis.benchmark_return_pct,
        excess_return_pct=kpis.excess_return_pct,
    )


def _summary_fingerprint(stats: SessionSummaryStats) -> str:
    """Deterministic SHA-256 over the stop-stable stats the narrative derives from.

    Hashes a canonical JSON payload of the summary's user-visible figures plus the stop
    metadata — deliberately excluding anything that drifts after the stop — so a stopped
    session's narrative is generated once and reused until the underlying figures change.
    """
    payload = {
        "stop_reason": stats.stop_reason,
        "stopped_at": stats.stopped_at.isoformat() if stats.stopped_at else None,
        "lifespan_days": stats.lifespan_days,
        "final_value": round(stats.final_value, 2),
        "allocated_capital": round(stats.allocated_capital, 2),
        "total_return": round(stats.total_return, 2),
        "total_return_pct": round(stats.total_return_pct, 6),
        "realised_pnl": round(stats.realised_pnl, 2),
        "peak_value": round(stats.peak_value, 2),
        "max_drawdown": round(stats.max_drawdown, 6),
        "trade_count": stats.trade_count,
        "win_rate": round(stats.win_rate, 6) if stats.win_rate is not None else None,
        "best_trade": _trade_fingerprint(stats.best_trade),
        "worst_trade": _trade_fingerprint(stats.worst_trade),
        "benchmark": stats.benchmark,
        "benchmark_return_pct": (
            round(stats.benchmark_return_pct, 6)
            if stats.benchmark_return_pct is not None
            else None
        ),
        "excess_return_pct": (
            round(stats.excess_return_pct, 6)
            if stats.excess_return_pct is not None
            else None
        ),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _trade_fingerprint(trade: TradeExtreme | None) -> dict[str, object] | None:
    """Canonical fingerprint payload for a single round-trip (or ``None``)."""
    if trade is None:
        return None
    return {
        "ticker": trade.ticker,
        "realised_pnl": round(trade.realised_pnl, 2),
        "quantity": round(trade.quantity, 6),
        "entry_price": round(trade.entry_price, 4),
        "entry_at": trade.entry_at.isoformat(),
        "exit_price": round(trade.exit_price, 4),
        "exit_at": trade.exit_at.isoformat(),
    }


def bot_session_summary(
    session: Session,
    bot: BotSession,
    agent: BotSessionSummaryAgent,
) -> BotSessionSummary:
    """Assemble a stopped session's summary, generating + caching its AI narrative.

    Raises :class:`BotSessionNotStoppedError` for a non-stopped session (no agent call).
    Otherwise it assembles the stats block, computes a stop-stable fingerprint, and:
    returns the cached narrative when the stored fingerprint matches; else calls the
    agent, persists the narrative + fingerprint + model + timestamp, and returns it. An
    agent failure is swallowed — the stats are returned with ``narrative=None`` and
    nothing is persisted, so a later view retries.
    """
    if bot.status != BotSessionStatus.STOPPED.value:
        raise BotSessionNotStoppedError(
            "a session summary is only available for a stopped session"
        )

    stats = bot_session_summary_stats(session, bot)
    fingerprint = _summary_fingerprint(stats)

    if (
        bot.summary_narrative is not None
        and bot.summary_fingerprint == fingerprint
    ):
        return BotSessionSummary(
            stats=stats,
            narrative=bot.summary_narrative,
            model=bot.summary_model,
            generated_at=bot.summary_generated_at,
        )

    try:
        with llm_trace(f"bot-summary-{fingerprint}"):
            output = agent.summarize(stats)
    except BotSummaryUnavailableError:
        # Leave any prior cached narrative untouched; serve stats without a fresh one.
        return BotSessionSummary(
            stats=stats, narrative=None, model=None, generated_at=None
        )

    narrative = f"**{output.headline}**\n\n{output.narrative}"
    generated_at = datetime.now(UTC)
    bot.summary_narrative = narrative
    bot.summary_fingerprint = fingerprint
    bot.summary_model = get_bot_summary_model()
    bot.summary_generated_at = generated_at
    session.flush()
    return BotSessionSummary(
        stats=stats,
        narrative=narrative,
        model=bot.summary_model,
        generated_at=generated_at,
    )


# Dashboard comparison seam ----------------------------------------------
def dashboard_performance(
    session: Session,
    bot: BotSession,
    *,
    range_: DashboardRange,
    today: date | None = None,
) -> SessionPerformance:
    """Adapt a bot session to a ``SessionPerformance`` row for the dashboard.

    Mirrors the AI-session adapter so the overview can union both sources: the
    range-windowed value series from the bot's own snapshots, the single opening
    contribution (v1 has no capital-increase path), and the contribution-aware
    buy-and-hold benchmark value — reusing ``load_benchmark_series`` /
    ``rebased_benchmark_value``. Tagged ``kind='bot'``.
    """
    as_of = today or datetime.now(UTC).date()
    start_date = resolve_range_start(range_, today=as_of)
    snapshots = list_bot_snapshots(session, bot)
    allocated = bot.allocated_capital

    # Point-in-time value is the session's freshest captured observation (latest
    # intraday value point when newer than the latest daily snapshot, else the
    # snapshot), so bot rows are live on the same basis as AI rows — not pinned
    # to the last end-of-day snapshot. The plotted series below stays daily.
    observation = latest_value_observation(session, bot)
    if observation is not None:
        current_value = observation.total_value
        unrealised = observation.unrealised_pnl
    else:
        current_value = total_value(bot, {})
        unrealised = 0.0

    # Value series windowed to the range (oldest first). With no snapshot yet,
    # anchor a single live point so the equity line stays aligned with the
    # benchmark overlay until the first snapshot lands.
    if snapshots:
        points = [
            SessionValuePoint(date=s.snapshot_date, value=s.total_value)
            for s in snapshots
            if start_date is None or s.snapshot_date >= start_date
        ]
    else:
        points = [SessionValuePoint(date=as_of, value=current_value)]

    # Baseline for the range pnl: the latest snapshot on/before the start date,
    # else the allocated capital (also the Max baseline).
    if start_date is None:
        value_start = allocated
    else:
        prior = [s.total_value for s in snapshots if s.snapshot_date <= start_date]
        value_start = prior[-1] if prior else allocated
    pnl = current_value - value_start

    # Single opening contribution, anchored at the first snapshot date (or the
    # as-of date before any snapshot), so fresh cash is never read as profit.
    contrib_date = snapshots[0].snapshot_date if snapshots else as_of
    contributions = [
        SessionContribution(effective_date=contrib_date, amount=allocated)
    ]

    benchmark_value = rebased_benchmark_value(
        load_benchmark_series(session, bot.benchmark),
        contributions=[
            Contribution(effective_date=contrib_date, amount=allocated)
        ],
        as_of=as_of,
    )

    label = bot_display_name(bot)

    return SessionPerformance(
        id=bot.id,
        label=label,
        allocated_capital=allocated,
        current_value=current_value,
        pnl=pnl,
        realised_pnl=bot.realised_pnl,
        unrealised_pnl=unrealised,
        fees=bot.total_fees,
        points=points,
        contributions=contributions,
        benchmark_value=benchmark_value,
        kind="bot",
    )


def dashboard_performances(
    session: Session,
    *,
    range_: DashboardRange,
    today: date | None = None,
) -> list[SessionPerformance]:
    """Dashboard rows for every active **manually created** bot (``kind='bot'``).

    Bots deployed by a bot orchestrator are excluded: the orchestrator's own row (see
    :mod:`cadence.bot_orchestrator.dashboard`) covers them, so their money is counted
    exactly once.
    """
    return [
        dashboard_performance(session, bot, range_=range_, today=today)
        for bot in active_bot_sessions(session)
        if bot.orchestrator_id is None
    ]
