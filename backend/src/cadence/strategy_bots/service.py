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

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cadence.assets import service as assets_service
from cadence.assets.category import AssetCategory, AssetMembership
from cadence.assets.models import Asset
from cadence.broker.base import Broker
from cadence.broker.models import AssetClass, OrderSide
from cadence.config import settings
from cadence.dashboard.constants import DashboardRange, resolve_range_start
from cadence.dashboard.service import (
    SessionContribution,
    SessionPerformance,
    SessionValuePoint,
)
from cadence.notify.base import Notifier
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
from cadence.strategy_bots import registry
from cadence.strategy_bots.constants import (
    BotSessionStatus,
    BotValueResolution,
    SizingMethod,
)
from cadence.strategy_bots.engine import (
    REASON_DRAWDOWN,
    ExecutionEngine,
    take_profit_stop_loss_reason,
    total_value,
    unrealised_pnl,
)
from cadence.strategy_bots.errors import (
    BotSessionNotArchivableError,
    BotSessionNotFoundError,
    IneligibleAssetError,
    InvalidBotBenchmarkError,
    InvalidBotConfigError,
)
from cadence.strategy_bots.market_data import MarketData
from cadence.strategy_bots.models import (
    BotSession,
    BotSymbol,
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
from cadence.strategy_bots.sizing import (
    EntryCandidate,
    atr,
    plan_entries,
)
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction


@dataclass(frozen=True)
class TickResult:
    """Summary of one tick run."""

    market_open: bool
    #: Active sessions that were evaluated and had the engine applied.
    processed: int = 0
    #: Active sessions skipped because fresh bars were unavailable.
    skipped: int = 0


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
    """A single closed round-trip trade, identified by ticker and its realized P&L."""

    ticker: str
    realised_pnl: float


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


def _trade_symbol(asset: Asset) -> str:
    """The broker/market-data symbol for an asset (Alpaca form when known)."""
    return asset.alpaca_symbol or asset.ticker


def _traded_set_label(bot: BotSession) -> str:
    """A short label for a session's traded set: the ticker if one, else a count."""
    if len(bot.symbols) == 1:
        return bot.symbols[0].ticker
    return f"{len(bot.symbols)} symbols"


def _bot_label(bot: BotSession) -> str:
    """The session's display label (explicit label, else strategy · traded set)."""
    if bot.label:
        return bot.label
    registration = registry.get_strategy(bot.strategy_key)
    return f"{registration.display_name} · {_traded_set_label(bot)}"


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


def _resolve_universe_equities(session: Session) -> list[Asset]:
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
    strategy_key: str,
    initial_capital: float,
    benchmark: str,
    tickers: list[str] | None = None,
    whole_universe: bool = False,
    strategy_params: dict[str, object] | None = None,
    label: str | None = None,
    take_profit_pct: float | None = None,
    stop_loss_pct: float | None = None,
    drawdown_stop_pct: float | None = None,
    cash_buffer_pct: float | None = None,
    sizing_method: str | None = None,
    risk_pct: float | None = None,
    atr_period: int | None = None,
    atr_k: float | None = None,
    max_position_pct: float | None = None,
    max_positions: int | None = None,
) -> BotSession:
    """Create and persist an active multi-asset bot session, validating every input.

    The traded set is either the given ``tickers`` (each validated as an eligible
    universe equity) or, when ``whole_universe`` is set, the currently eligible universe
    equities resolved at creation. ``initial_capital`` becomes the session's shared cash
    pool and hard budget. Raises ``UnknownStrategyError`` for an unregistered strategy,
    ``InvalidStrategyParamsError`` for bad params, ``InvalidBotBenchmarkError`` for an
    unknown benchmark, ``IneligibleAssetError`` for a non-eligible / non-equity asset,
    and ``InvalidBotConfigError`` for an empty set or an unknown sizing method. No AI
    model is invoked.
    """
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
        assets = _resolve_universe_equities(session)
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


def stop_bot_session(session: Session, bot_id: uuid.UUID) -> BotSession:
    """Stop an active session so it is no longer ticked (idempotent)."""
    bot = get_bot_session(session, bot_id)
    if bot.status == BotSessionStatus.ACTIVE.value:
        bot.status = BotSessionStatus.STOPPED.value
    session.flush()
    return bot


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
        bot.last_tick_at = tick_now
        _record_value_point(session, bot, marks, captured_at=tick_now)
        _notify_safely(
            notifier,
            title=f"Cadence bot: {_bot_label(bot)} drawdown kill-switch",
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
    """Advance every active bot session once (stateless recompute).

    No-op when the equity market is closed. For each active session it fetches each
    traded symbol's required bar history from ``market_data`` at the configured
    timeframe, processes exits before entries, and sizes entries from the shared cash
    pool. A session with no fresh symbol data is counted as skipped. When a session's
    drawdown kill-switch trips, a best-effort notification is sent via ``notifier``
    (a ``None`` notifier stays silent and a notifier failure never fails the tick).
    """
    if not broker.is_market_open():
        return TickResult(market_open=False)

    tick_now = now or datetime.now(UTC)
    engine = ExecutionEngine(session, broker)

    processed = 0
    skipped = 0
    for bot in active_bot_sessions(session):
        if _tick_session(
            bot,
            session=session,
            engine=engine,
            market_data=market_data,
            tick_now=tick_now,
            notifier=notifier,
        ):
            processed += 1
        else:
            skipped += 1

    session.flush()
    return TickResult(market_open=True, processed=processed, skipped=skipped)


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


def _bot_daily_pnl(
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


def _bot_benchmark_suffix(
    session: Session,
    bot: BotSession,
    snapshots: list[BotValueSnapshot],
    *,
    total_return_pct: float,
    as_of: date,
) -> str | None:
    """Benchmark comparison suffix for a bot's daily summary line, or ``None``.

    A simple since-inception buy-and-hold benchmark return (bots have no capital-
    increase events, so no time-weighting is needed) compared against the bot's own
    total return. Returns ``None`` when the session has no snapshots or the benchmark
    lacks usable stored closes, so the caller omits the suffix.
    """
    if not snapshots:
        return None
    series = load_benchmark_series(session, bot.benchmark)
    benchmark_return = benchmark_return_fraction(
        series, start_date=snapshots[0].snapshot_date, as_of=as_of
    )
    if benchmark_return is None:
        return None
    excess = total_return_pct - benchmark_return
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
) -> int:
    """Record a daily value snapshot for every active session; return the count.

    For each snapshotted session it also sends one best-effort daily-summary push via
    ``notifier`` (one per bot, no cross-bot roll-up) mirroring the AI daily report —
    value and day-over-day change, total return, realised/unrealised P&L, cash, fees,
    Sharpe, a benchmark comparison, the best/worst open position, and the number of
    trades executed that day. A ``None`` notifier stays silent and a notifier failure
    never fails the snapshot job.
    """
    when = (now or datetime.now(UTC)).date()
    count = 0
    for bot in active_bot_sessions(session):
        marks = _mark_positions(bot, broker)
        snapshot = record_bot_snapshot(
            session, bot, marks=marks, snapshot_date=when
        )
        count += 1

        kpis = bot_session_kpis(session, bot)
        daily_pnl, daily_pnl_pct = _bot_daily_pnl(session, bot, snapshot)
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
            title=f"Cadence bot: {_bot_label(bot)} daily P&L",
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
    session.flush()
    return count


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


def bot_current_value(session: Session, bot: BotSession) -> float:
    """A session's current value: cash plus its marked-to-market open positions.

    Reads the session's latest recorded value snapshot when one exists (already
    marked-to-market at capture); before any snapshot exists it falls back to cash
    plus open positions valued at cost. This is the single source of truth for a
    session's current value, shared by the per-session KPIs and the session list.
    """
    snapshots = list_bot_snapshots(session, bot)
    if snapshots:
        return snapshots[-1].total_value
    # No snapshot yet: cash plus positions marked at cost.
    return total_value(bot, {})


def bot_trade_extremes(
    session: Session, bot: BotSession
) -> tuple[TradeExtreme | None, TradeExtreme | None]:
    """The session's best and worst closed round-trip by realized P&L.

    Walks the ledger oldest-first, pairing each sell (a full exit) with its ticker's
    open entry basis; a round-trip's realized P&L is the exit proceeds minus the entry
    cost, net of both fills' fees. Returns ``(best, worst)`` — the max- and min-P&L
    round-trips — or ``(None, None)`` when no position has been closed yet. Relies on
    the one-position-per-symbol + full-exit invariants, so each ticker's fills strictly
    alternate buy → sell.
    """
    stmt = (
        select(BotTrade)
        .where(BotTrade.bot_session_id == bot.id)
        .order_by(BotTrade.created_at, BotTrade.id)
    )
    # ticker -> (entry price, entry quantity, entry fees) for its open position.
    open_basis: dict[str, tuple[float, float, float]] = {}
    round_trips: list[TradeExtreme] = []
    for trade in session.execute(stmt).scalars():
        if trade.filled_price is None:
            continue
        if trade.side == OrderSide.BUY.value:
            open_basis[trade.ticker] = (
                trade.filled_price,
                trade.quantity,
                trade.fees,
            )
        else:  # sell — closes this ticker's open position
            entry = open_basis.pop(trade.ticker, None)
            if entry is None:
                continue
            entry_price, _entry_qty, entry_fees = entry
            pnl = (
                (trade.filled_price - entry_price) * trade.quantity
                - entry_fees
                - trade.fees
            )
            round_trips.append(TradeExtreme(ticker=trade.ticker, realised_pnl=pnl))
    if not round_trips:
        return None, None
    best = max(round_trips, key=lambda t: t.realised_pnl)
    worst = min(round_trips, key=lambda t: t.realised_pnl)
    return best, worst


def bot_session_kpis(session: Session, bot: BotSession) -> BotKpis:
    """Compute KPIs for a session from its own ledger and value snapshots."""
    snapshots = list_bot_snapshots(session, bot)
    if snapshots:
        latest = snapshots[-1]
        current_value = latest.total_value
        unrealised = latest.unrealised_pnl
    else:
        # No snapshot yet: cash plus positions marked at cost (zero unrealised).
        current_value = total_value(bot, {})
        unrealised = 0.0

    total_return = current_value - bot.allocated_capital
    total_return_pct = (
        total_return / bot.allocated_capital
        if bot.allocated_capital
        else 0.0
    )
    best_trade, worst_trade = bot_trade_extremes(session, bot)
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

    if snapshots:
        current_value = snapshots[-1].total_value
        unrealised = snapshots[-1].unrealised_pnl
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

    label = _bot_label(bot)

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
    """Dashboard performance rows for every active bot session (``kind='bot'``)."""
    return [
        dashboard_performance(session, bot, range_=range_, today=today)
        for bot in active_bot_sessions(session)
    ]
