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
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.assets import service as assets_service
from cadence.assets.category import AssetCategory, AssetMembership
from cadence.assets.models import Asset
from cadence.broker.base import Broker
from cadence.broker.models import AssetClass
from cadence.config import settings
from cadence.dashboard.constants import DashboardRange, resolve_range_start
from cadence.dashboard.service import (
    SessionContribution,
    SessionPerformance,
    SessionValuePoint,
)
from cadence.paper_trading.benchmark import (
    Contribution,
    load_benchmark_series,
    rebased_benchmark_value,
)
from cadence.paper_trading.constants import Benchmark
from cadence.strategy_bots import registry
from cadence.strategy_bots.constants import BotSessionStatus
from cadence.strategy_bots.engine import (
    ExecutionEngine,
    total_value,
    unrealised_pnl,
)
from cadence.strategy_bots.errors import (
    BotSessionNotArchivableError,
    BotSessionNotFoundError,
    IneligibleAssetError,
    InvalidBotBenchmarkError,
)
from cadence.strategy_bots.market_data import MarketData
from cadence.strategy_bots.models import (
    BotSession,
    BotValueSnapshot,
)
from cadence.strategy_bots.strategy import PositionView


@dataclass(frozen=True)
class TickResult:
    """Summary of one tick run."""

    market_open: bool
    #: Active sessions that were evaluated and had the engine applied.
    processed: int = 0
    #: Active sessions skipped because fresh bars were unavailable.
    skipped: int = 0


@dataclass(frozen=True)
class BotKpis:
    """Performance figures for a bot session, from its own ledger + snapshots."""

    current_value: float
    allocated_capital: float
    total_return: float
    total_return_pct: float
    realised_pnl: float
    unrealised_pnl: float
    total_fees: float
    total_trades: int
    max_drawdown: float


def _trade_symbol(asset: Asset) -> str:
    """The broker/market-data symbol for an asset (Alpaca form when known)."""
    return asset.alpaca_symbol or asset.ticker


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


def create_bot_session(
    session: Session,
    *,
    strategy_key: str,
    ticker: str,
    initial_capital: float,
    benchmark: str,
    strategy_params: dict[str, object] | None = None,
    label: str | None = None,
    take_profit_pct: float | None = None,
    stop_loss_pct: float | None = None,
    drawdown_stop_pct: float | None = None,
    cash_buffer_pct: float | None = None,
) -> BotSession:
    """Create and persist an active bot session, validating every input.

    Raises ``UnknownStrategyError`` for an unregistered strategy,
    ``InvalidStrategyParamsError`` for bad params, ``InvalidBotBenchmarkError`` for
    an unknown benchmark, and ``IneligibleAssetError`` for a non-eligible or
    non-equity asset. No AI model is invoked.
    """
    registration = registry.get_strategy(strategy_key)
    params = registration.parse_params(strategy_params or {})

    try:
        benchmark_enum = Benchmark(benchmark)
    except ValueError as exc:
        raise InvalidBotBenchmarkError(
            f"{benchmark!r} is not a known benchmark"
        ) from exc

    asset = _resolve_equity_asset(session, ticker)

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
        asset_id=asset.id,
        ticker=asset.ticker,
        label=label,
        status=BotSessionStatus.ACTIVE.value,
        benchmark=benchmark_enum.value,
        initial_capital=initial_capital,
        allocated_capital=initial_capital,
        strategy_params=params.model_dump(),
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        drawdown_stop_pct=drawdown,
        cash_buffer_pct=buffer,
        peak_value=initial_capital,
    )
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
def run_tick(
    session: Session,
    *,
    broker: Broker,
    market_data: MarketData,
    now: datetime | None = None,
) -> TickResult:
    """Advance every active bot session once (stateless recompute).

    No-op when the equity market is closed. For each active session it fetches the
    strategy's required bar history from ``market_data`` at the configured
    timeframe, skips the session if the data is not fresh, recomputes indicators,
    evaluates the strategy, and runs the execution engine.
    """
    if not broker.is_market_open():
        return TickResult(market_open=False)

    tick_now = now or datetime.now(UTC)
    timeframe = settings.BOT_SIGNAL_BAR_TIMEFRAME
    engine = ExecutionEngine(session, broker)

    processed = 0
    skipped = 0
    for bot in active_bot_sessions(session):
        registration = registry.get_strategy(bot.strategy_key)
        params = registration.parse_params(bot.strategy_params)
        asset = session.get(Asset, bot.asset_id)
        symbol = _trade_symbol(asset) if asset is not None else bot.ticker

        result = market_data.latest_bars(
            symbol, timeframe, params.required_history, now=tick_now
        )
        if not result.fresh or not result.bars:
            # Stale/missing data: skip, leaving position + ledger unchanged.
            skipped += 1
            continue

        price = result.bars[-1].close
        position = (
            None
            if bot.is_flat
            else PositionView(
                quantity=bot.position_qty or 0.0,
                avg_price=bot.position_avg_price or 0.0,
            )
        )
        signal = registration.strategy.evaluate(result.bars, position, params)
        engine.run(bot, signal, price, now=tick_now, symbol=symbol)
        processed += 1

    session.flush()
    return TickResult(market_open=True, processed=processed, skipped=skipped)


# Snapshots & KPIs --------------------------------------------------------
def _session_mark_price(bot: BotSession, broker: Broker) -> float:
    """Latest price to mark the position (0 is fine when the session is flat)."""
    if bot.is_flat:
        return 0.0
    quote = broker.get_quote(bot.ticker, AssetClass.EQUITY)
    price = quote.last if quote.last is not None else quote.mid
    return price if price is not None else (bot.position_avg_price or 0.0)


def record_bot_snapshot(
    session: Session,
    bot: BotSession,
    *,
    price: float,
    snapshot_date: date | None = None,
) -> BotValueSnapshot:
    """Upsert the daily value snapshot for ``bot`` (one row per session per day)."""
    when = snapshot_date or datetime.now(UTC).date()
    value = total_value(bot, price)
    unrealised = unrealised_pnl(bot, price)

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


def run_bot_snapshots(
    session: Session,
    *,
    broker: Broker,
    now: datetime | None = None,
) -> int:
    """Record a daily value snapshot for every active session; return the count."""
    when = (now or datetime.now(UTC)).date()
    count = 0
    for bot in active_bot_sessions(session):
        price = _session_mark_price(bot, broker)
        record_bot_snapshot(session, bot, price=price, snapshot_date=when)
        count += 1
    session.flush()
    return count


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


def bot_session_kpis(session: Session, bot: BotSession) -> BotKpis:
    """Compute KPIs for a session from its own ledger and value snapshots."""
    snapshots = list_bot_snapshots(session, bot)
    if snapshots:
        latest = snapshots[-1]
        current_value = latest.total_value
        unrealised = latest.unrealised_pnl
    else:
        # No snapshot yet: value is cash only (flat at inception).
        current_value = (
            bot.allocated_capital + bot.realised_pnl - bot.total_fees
        )
        unrealised = 0.0

    total_return = current_value - bot.allocated_capital
    total_return_pct = (
        total_return / bot.allocated_capital
        if bot.allocated_capital
        else 0.0
    )
    return BotKpis(
        current_value=current_value,
        allocated_capital=bot.allocated_capital,
        total_return=total_return,
        total_return_pct=total_return_pct,
        realised_pnl=bot.realised_pnl,
        unrealised_pnl=unrealised,
        total_fees=bot.total_fees,
        total_trades=bot.total_trades,
        max_drawdown=_max_drawdown([s.total_value for s in snapshots]),
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
        current_value = allocated + bot.realised_pnl - bot.total_fees
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

    registration = registry.get_strategy(bot.strategy_key)
    label = bot.label or f"{registration.display_name} · {bot.ticker}"

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
