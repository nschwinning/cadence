"""Paper-trading service/repository: business logic and data access.

Routers stay thin and delegate here. All DB access for the paper-trading domain
lives in this module. These functions port trading-bot's repository methods to
service functions operating on a SQLAlchemy :class:`Session`.
"""

from __future__ import annotations

import logging
import statistics
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cadence.assets.category import AssetCategory, AssetScope, scope_categories
from cadence.assets.models import Asset
from cadence.assets.service import normalize_ticker
from cadence.broker.base import Broker
from cadence.broker.models import AssetClass, OrderSide, OrderStatus, Position
from cadence.config import settings
from cadence.paper_trading.benchmark import (
    Contribution,
    benchmark_return_fraction,
    load_benchmark_series,
    rebased_benchmark_value,
)
from cadence.paper_trading.constants import (
    SHARPE_MIN_RETURNS,
    SHARPE_TRADING_DAYS_PER_YEAR,
    TERMINAL_ORDER_STATUSES,
    Benchmark,
    RunStatus,
    ScheduleMode,
    SessionStatus,
)
from cadence.paper_trading.errors import (
    DuplicateSessionError,
    InvalidAssetScopeError,
    InvalidBenchmarkError,
    InvalidCapitalChangeError,
    SessionNotArchivableError,
    SessionNotFoundError,
)
from cadence.paper_trading.models import (
    ClosedPosition,
    PaperTrade,
    PaperTradingSession,
    SessionCapitalEvent,
    SessionDailyRunSnapshot,
    SessionPosition,
    SessionRun,
    SessionValueSnapshot,
    StopLossQuarantine,
)

logger = logging.getLogger(__name__)

# Default seed capital for a new session (mirrors trading-bot).
DEFAULT_ALLOCATED_CAPITAL = 100000.0

# Tags for trades/runs produced by a scope-narrowing liquidation (no AI event).
SCOPE_CHANGE_SIGNAL_TYPE = "scope_change_sell"
SCOPE_CHANGE_RUN_TRIGGER = "scope_change"

# A ledger position whose remaining quantity falls at or below this is treated as
# fully exited and its row removed. Sized to the executor's crypto quantity
# precision (8 decimals) so fractional dust nets cleanly to a closed position.
LEDGER_QUANTITY_EPSILON = 1e-8


def create_session(
    session: Session,
    *,
    portfolio_id: uuid.UUID,
    strategy_key: str,
    rebalance_prompt_version: int,
    crypto_rebalance_prompt_version: int,
    benchmark: Benchmark,
    allocated_capital: float = DEFAULT_ALLOCATED_CAPITAL,
    max_allocation_pct: float = 1.0,
    schedule_mode: ScheduleMode = ScheduleMode.SCHEDULED,
    use_technical_indicators: bool = False,
    stop_loss_enabled: bool = False,
    stop_loss_pct: float | None = None,
    risk_guardrails_enabled: bool = False,
    max_asset_class_pct: float | None = None,
    min_positions: int | None = None,
    max_invested_pct: float | None = None,
    learning_feedback_enabled: bool = False,
    learning_feedback_window: int | None = None,
) -> PaperTradingSession:
    """Create a paper-trading session for a ``(portfolio, strategy)`` pair.

    ``rebalance_prompt_version`` freezes the rebalance-prompt version this session
    will always use; callers pass the version that is active at build time.
    ``crypto_rebalance_prompt_version`` likewise freezes the ``crypto_rebalance``-kind
    prompt version used by the weekend crypto-only rebalance.
    ``benchmark`` is the market index the session is compared against (the build
    passes the chosen/default id). ``use_technical_indicators`` freezes the
    technical-indicator trend-strategy opt-in at build time (default off); every
    later rebalance reads it back rather than re-deciding. ``stop_loss_enabled``
    and ``stop_loss_pct`` likewise freeze the automatic hard stop-loss opt-in and
    its threshold at build time (default off / no threshold).
    ``risk_guardrails_enabled`` freezes the opt-in for the deterministic portfolio
    risk guardrails; when enabled, ``max_allocation_pct`` (per-asset cap),
    ``max_asset_class_pct``, ``min_positions``, and ``max_invested_pct`` freeze the
    guardrail parameters. When disabled these params stay None / ``max_allocation_pct``
    stays its 1.0 no-op default, and every later rebalance reads them back rather
    than re-deciding. ``learning_feedback_enabled`` and ``learning_feedback_window``
    freeze the learning-feedback opt-in and its window at build time (default off /
    no window); when enabled, the rebalance agent is shown an advisory summary of the
    session's own recent daily-run outcomes.

    Raises:
        DuplicateSessionError: if a session already exists for the same
            ``(portfolio_id, strategy_key)`` (the UNIQUE constraint).
    """
    row = PaperTradingSession(
        portfolio_id=portfolio_id,
        strategy_key=strategy_key,
        status=SessionStatus.ACTIVE.value,
        allocated_capital=allocated_capital,
        max_allocation_pct=max_allocation_pct,
        schedule_mode=schedule_mode.value,
        rebalance_prompt_version=rebalance_prompt_version,
        crypto_rebalance_prompt_version=crypto_rebalance_prompt_version,
        benchmark=benchmark.value,
        use_technical_indicators=use_technical_indicators,
        stop_loss_enabled=stop_loss_enabled,
        stop_loss_pct=stop_loss_pct,
        risk_guardrails_enabled=risk_guardrails_enabled,
        max_asset_class_pct=max_asset_class_pct,
        min_positions=min_positions,
        max_invested_pct=max_invested_pct,
        learning_feedback_enabled=learning_feedback_enabled,
        learning_feedback_window=learning_feedback_window,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateSessionError(
            f"A session already exists for portfolio {portfolio_id} "
            f"and strategy {strategy_key!r}"
        ) from exc
    session.refresh(row)
    return row


def get_session(session: Session, session_id: uuid.UUID) -> PaperTradingSession:
    """Return a session by id or raise :class:`SessionNotFoundError`."""
    row = session.get(PaperTradingSession, session_id)
    if row is None:
        raise SessionNotFoundError(f"Paper trading session {session_id} not found")
    return row


def list_sessions(
    session: Session,
    *,
    status: SessionStatus | None = None,
    include_archived: bool = False,
    limit: int = 50,
) -> list[PaperTradingSession]:
    """List sessions, most recently updated first, optionally filtered by status.

    Archived sessions are excluded unless ``include_archived`` is set; the archived
    filter composes with the optional ``status`` filter.
    """
    stmt = select(PaperTradingSession).order_by(
        PaperTradingSession.updated_at.desc(), PaperTradingSession.id.desc()
    )
    if status is not None:
        stmt = stmt.where(PaperTradingSession.status == status.value)
    if not include_archived:
        stmt = stmt.where(PaperTradingSession.archived_at.is_(None))
    return list(session.execute(stmt.limit(limit)).scalars())


def count_sessions(
    session: Session,
    *,
    status: SessionStatus | None = None,
    include_archived: bool = False,
) -> int:
    """Count sessions, optionally filtered by status; excludes archived by default."""
    stmt = select(func.count()).select_from(PaperTradingSession)
    if status is not None:
        stmt = stmt.where(PaperTradingSession.status == status.value)
    if not include_archived:
        stmt = stmt.where(PaperTradingSession.archived_at.is_(None))
    return session.execute(stmt).scalar_one()


def update_session_status(
    session: Session,
    session_id: uuid.UUID,
    status: SessionStatus,
) -> PaperTradingSession:
    """Update a session's status. Raises if the session does not exist."""
    row = get_session(session, session_id)
    row.status = status.value
    session.commit()
    session.refresh(row)
    return row


def archive_session(
    session: Session, session_id: uuid.UUID
) -> PaperTradingSession:
    """Soft-archive a stopped session by stamping ``archived_at``.

    Raises:
        SessionNotFoundError: if no session has ``session_id``.
        SessionNotArchivableError: if the session's status is not stopped.
    """
    row = get_session(session, session_id)
    if row.status != SessionStatus.STOPPED.value:
        raise SessionNotArchivableError(
            f"Session {session_id} must be stopped before it can be archived"
        )
    row.archived_at = datetime.now(tz=UTC)
    session.commit()
    session.refresh(row)
    return row


def unarchive_session(
    session: Session, session_id: uuid.UUID
) -> PaperTradingSession:
    """Clear a session's ``archived_at``, restoring it to the default listing.

    Unconditional (any archived session may be unarchived); the session's status is
    unchanged. Raises :class:`SessionNotFoundError` for an unknown id.
    """
    row = get_session(session, session_id)
    row.archived_at = None
    session.commit()
    session.refresh(row)
    return row


def change_session_benchmark(
    session: Session, session_id: uuid.UUID, benchmark: str
) -> PaperTradingSession:
    """Change the benchmark a session is compared against.

    ``benchmark`` must be a valid :class:`Benchmark` id. Only the pointer changes;
    the session's trades, positions, and value snapshots are untouched, so later
    reads recompute comparisons against the new series.

    Raises:
        SessionNotFoundError: if no session has ``session_id``.
        InvalidBenchmarkError: if ``benchmark`` is not in the catalog (the session's
            benchmark is left unchanged).
    """
    try:
        resolved = Benchmark(benchmark)
    except ValueError as exc:
        allowed = ", ".join(b.value for b in Benchmark)
        raise InvalidBenchmarkError(
            f"benchmark must be one of: {allowed}"
        ) from exc
    row = get_session(session, session_id)
    row.benchmark = resolved.value
    session.commit()
    session.refresh(row)
    return row


def change_session_scope(
    session: Session,
    *,
    session_id: uuid.UUID,
    scope: str,
    broker: Broker,
) -> PaperTradingSession:
    """Change a session's asset scope, liquidating now-out-of-scope holdings.

    ``scope`` must be a valid :class:`AssetScope` value ('stocks', 'crypto', or
    'both'). The new scope is persisted into ``session_metadata["asset_types"]`` so
    every scope-keyed read — AI builds and rebalances, the weekend crypto cron, and
    weekend snapshot gating — honors it on the next run (they all re-read metadata).

    When the new scope EXCLUDES the asset class of any open position (a narrowing),
    those positions are sold through ``broker`` *before* the scope is committed —
    each sale recorded with the standard per-trade transaction cost and the
    session's recorded value refreshed. Widening the scope, or a change that
    excludes nothing held, liquidates nothing. Changing to the current scope is a
    successful no-op.

    Raises:
        InvalidAssetScopeError: if ``scope`` is not a supported scope (the session
            is left unchanged).
        SessionNotFoundError: if no session has ``session_id``.
        cadence.broker.ConnectionError: if a required liquidation cannot reach the
            broker (the scope is left unchanged); mapped to 503 by the app handler.
    """
    try:
        resolved = AssetScope(scope)
    except ValueError as exc:
        allowed = ", ".join(s.value for s in AssetScope)
        raise InvalidAssetScopeError(
            f"asset_types must be one of: {allowed}"
        ) from exc

    row = get_session(session, session_id)
    current = (row.session_metadata or {}).get("asset_types", AssetScope.BOTH.value)
    if current == resolved.value:
        return row  # no-op: unchanged scope never liquidates or mutates the session

    # Sell any held position the new scope excludes before persisting the change, so
    # a broker outage fails the request rather than recording an un-liquidated
    # narrowing.
    _liquidate_out_of_scope_positions(session, row, resolved, broker=broker)

    # Persist the new scope by reassigning the JSON dict so SQLAlchemy flushes it.
    metadata = dict(row.session_metadata or {})
    metadata["asset_types"] = resolved.value
    row.session_metadata = metadata
    session.commit()
    session.refresh(row)
    return row


def increase_session_capital(
    session: Session,
    *,
    session_id: uuid.UUID,
    amount: float,
) -> PaperTradingSession:
    """Increase a session's capital, recording the contribution in the ledger.

    Appends one :class:`SessionCapitalEvent` (effective today, UTC) and raises the
    session's ``allocated_capital`` by ``amount`` in the same transaction, so the
    derived cash (:func:`compute_session_value`) rises by ``amount`` and the next
    scheduled rebalance — which sizes against live value — deploys it. No broker
    call: nothing is bought or sold on contribution.

    Increase-only: an ``amount`` at or below zero raises
    :class:`InvalidCapitalChangeError` and the session is left unchanged.

    Raises:
        SessionNotFoundError: if no session has ``session_id``.
        InvalidCapitalChangeError: if ``amount <= 0``.
    """
    if amount <= 0:
        raise InvalidCapitalChangeError(
            "capital increase amount must be positive"
        )
    row = get_session(session, session_id)
    event = SessionCapitalEvent(
        session_id=row.id,
        amount=amount,
        effective_date=datetime.now(tz=UTC).date(),
    )
    session.add(event)
    row.allocated_capital += amount
    session.commit()
    session.refresh(row)
    return row


def _liquidate_out_of_scope_positions(
    session: Session,
    session_row: PaperTradingSession,
    new_scope: AssetScope,
    *,
    broker: Broker,
) -> None:
    """Sell each open position whose asset class ``new_scope`` excludes.

    Mirrors the AI close / stop-loss recording path: each out-of-scope position is
    fully sold through the executor, the fill recorded with the flat transaction cost
    (into ``total_fees`` via :func:`record_trade`), the position closed in the ledger,
    and — when anything sold — the session's value snapshot refreshed. A position's
    class follows its asset record (crypto iff its category is crypto), matching the
    rebalance universe filter; tickers absent from the universe default to equity.
    Does nothing when nothing held is out of scope (a widening or no-op change).
    """
    from cadence.ai_portfolio.executor import AIPortfolioExecutor

    open_positions = [
        p for p in list_open_positions(session, session_row.id) if p.quantity
    ]
    if not open_positions:
        return

    allowed = scope_categories(new_scope)
    crypto_allowed = AssetCategory.CRYPTO in allowed
    equity_allowed = AssetCategory.STOCK in allowed

    tickers = [p.ticker for p in open_positions]
    category_by_ticker = {
        asset.ticker: asset.category
        for asset in session.execute(
            select(Asset).where(Asset.ticker.in_(tickers))
        ).scalars()
    }

    out_of_scope: list[tuple[SessionPosition, AssetClass]] = []
    for pos in open_positions:
        is_crypto = category_by_ticker.get(pos.ticker) == AssetCategory.CRYPTO.value
        if is_crypto and not crypto_allowed:
            out_of_scope.append((pos, AssetClass.CRYPTO))
        elif not is_crypto and not equity_allowed:
            out_of_scope.append((pos, AssetClass.EQUITY))

    if not out_of_scope:
        return

    # Probe broker reachability up front: execute_close swallows per-ticker errors,
    # so without this an unconfigured/unreachable broker would silently sell nothing
    # yet still let the caller persist the narrowing. A ConnectionError here (→ 503)
    # leaves the scope unchanged.
    broker.get_account_info()

    executor = AIPortfolioExecutor(broker, session_row.allocated_capital)
    now = datetime.now(tz=UTC)
    sold = 0
    realized_pnl_total = 0.0
    details: list[dict[str, Any]] = []

    for pos, cls in out_of_scope:
        position = Position(
            symbol=pos.ticker, quantity=pos.quantity, avg_cost=pos.avg_cost
        )
        results = executor.execute_close(
            {pos.ticker: position}, asset_classes={pos.ticker: cls}
        )
        details.extend(tr.to_dict() for tr in results)
        result = next((tr for tr in results if tr.executed), None)
        if result is None:
            continue

        fill_price = result.filled_price or result.price or 0.0
        record_trade(
            session,
            session_id=session_row.id,
            ticker=result.ticker,
            side=OrderSide.SELL,
            quantity=result.shares,
            price=result.price or 0.0,
            signal_type=SCOPE_CHANGE_SIGNAL_TYPE,
            asset_class=cls,
            order_id=result.order_id,
            order_status=result.order_status,
            filled_price=result.filled_price,
            ai_portfolio_event_id=None,
        )
        sold += 1

        basis = get_position_entry_basis(session, session_row.id, result.ticker)
        if basis is not None:
            entry_price, entry_date = basis
            closed = record_closed_position(
                session,
                session_id=session_row.id,
                ticker=result.ticker,
                quantity=result.shares,
                entry_price=entry_price,
                exit_price=fill_price or entry_price,
                entry_date=entry_date,
                exit_date=now,
                ai_portfolio_event_id=None,
            )
            realized_pnl_total += closed.realized_pnl

        apply_fill_to_ledger(
            session,
            session_id=session_row.id,
            ticker=result.ticker,
            side=OrderSide.SELL,
            shares=result.shares,
            price=fill_price,
        )

    if sold == 0:
        return

    record_session_run(
        session,
        session_id=session_row.id,
        signals_scanned=len(out_of_scope),
        signals_actionable=sold,
        orders_executed=sold,
        orders_skipped=len(out_of_scope) - sold,
        details=details,
        status=RunStatus.SUCCESS,
        run_trigger=SCOPE_CHANGE_RUN_TRIGGER,
    )
    update_session_last_run(
        session, session_row.id, trades_delta=sold, pnl_delta=realized_pnl_total
    )
    # Refresh the session's recorded value so the valuation reflects the sales.
    record_value_snapshot(
        session, session_id=session_row.id, as_of=now.date(), broker=broker
    )


def update_session_last_run(
    session: Session,
    session_id: uuid.UUID,
    *,
    trades_delta: int = 0,
    pnl_delta: float = 0.0,
) -> PaperTradingSession:
    """Stamp ``last_run_at`` and add to the running trade count / P&L totals."""
    row = get_session(session, session_id)
    row.last_run_at = datetime.now(tz=UTC)
    row.total_trades = row.total_trades + trades_delta
    row.total_pnl = row.total_pnl + pnl_delta
    session.commit()
    session.refresh(row)
    return row


def record_trade(
    session: Session,
    *,
    session_id: uuid.UUID,
    ticker: str,
    side: OrderSide,
    quantity: float,
    price: float,
    signal_type: str,
    asset_class: AssetClass,
    order_id: str | None = None,
    order_status: OrderStatus = OrderStatus.FILLED,
    filled_price: float | None = None,
    filled_at: datetime | None = None,
    ai_portfolio_event_id: uuid.UUID | None = None,
) -> PaperTrade:
    """Record a paper trade (fill). ``notional`` is derived as ``quantity * price``.

    ``ai_portfolio_event_id`` links the trade to the AI run that produced it; it is
    left NULL for non-AI strategies.

    Recording a trade also charges the session an asset-class-aware transaction
    cost into its cumulative ``total_fees``, matching Alpaca's fee schedule:
    equity (and any non-crypto) fills are free, while crypto fills are charged
    ``settings.CRYPTO_FEE_PCT`` of the executed notional (the filled price when
    present, else the quoted ``price``, times ``quantity``). This is the single
    choke point for persisting a trade, so every executed fill is charged
    correctly and skipped orders (never recorded) are correctly free.
    """
    trade = PaperTrade(
        session_id=session_id,
        ai_portfolio_event_id=ai_portfolio_event_id,
        ticker=ticker,
        side=side.value,
        quantity=quantity,
        price=price,
        notional=quantity * price,
        signal_type=signal_type,
        order_id=order_id,
        order_status=order_status.value,
        filled_price=filled_price,
        filled_at=filled_at,
    )
    session.add(trade)
    # Charge the asset-class-aware transaction cost onto the owning session:
    # crypto pays a percentage of executed notional; equities are free.
    if asset_class is AssetClass.CRYPTO:
        executed_price = filled_price if filled_price is not None else price
        fee = settings.CRYPTO_FEE_PCT * quantity * executed_price
    else:
        fee = 0.0
    # Record the per-trade fee on the trade itself (in addition to the session's
    # cumulative total) so the daily-run learning document can attribute cost per
    # order and per day.
    trade.fee = fee
    row = get_session(session, session_id)
    row.total_fees = row.total_fees + fee
    session.commit()
    session.refresh(trade)
    return trade


def get_session_trades(
    session: Session,
    session_id: uuid.UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[PaperTrade]:
    """Return a session's trades, most recent first.

    Paginated via ``limit``/``offset`` (pair with :func:`count_session_trades`).
    """
    stmt = (
        select(PaperTrade)
        .where(PaperTrade.session_id == session_id)
        .order_by(PaperTrade.executed_at.desc(), PaperTrade.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars())


def count_session_trades(session: Session, session_id: uuid.UUID) -> int:
    """Count a session's trades."""
    stmt = (
        select(func.count())
        .select_from(PaperTrade)
        .where(PaperTrade.session_id == session_id)
    )
    return session.execute(stmt).scalar_one()


def record_session_run(
    session: Session,
    *,
    session_id: uuid.UUID,
    signals_scanned: int = 0,
    signals_actionable: int = 0,
    orders_executed: int = 0,
    orders_skipped: int = 0,
    details: list[dict[str, Any]] | None = None,
    status: RunStatus = RunStatus.SUCCESS,
    run_trigger: str = "scheduled",
    duration_ms: int | None = None,
    ai_portfolio_event_id: uuid.UUID | None = None,
) -> SessionRun:
    """Record a session run (a single scan/rebalance)."""
    run = SessionRun(
        session_id=session_id,
        signals_scanned=signals_scanned,
        signals_actionable=signals_actionable,
        orders_executed=orders_executed,
        orders_skipped=orders_skipped,
        details=details,
        status=status.value,
        run_trigger=run_trigger,
        duration_ms=duration_ms,
        ai_portfolio_event_id=ai_portfolio_event_id,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_session_runs(
    session: Session,
    session_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[SessionRun]:
    """Return a session's run history, most recent first.

    Paginated via ``limit``/``offset`` (pair with :func:`count_session_runs`).
    """
    stmt = (
        select(SessionRun)
        .where(SessionRun.session_id == session_id)
        .order_by(SessionRun.run_at.desc(), SessionRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars())


def count_session_runs(session: Session, session_id: uuid.UUID) -> int:
    """Count a session's runs."""
    stmt = (
        select(func.count())
        .select_from(SessionRun)
        .where(SessionRun.session_id == session_id)
    )
    return session.execute(stmt).scalar_one()


def record_closed_position(
    session: Session,
    *,
    session_id: uuid.UUID,
    ticker: str,
    quantity: float,
    entry_price: float,
    exit_price: float,
    entry_date: datetime,
    exit_date: datetime,
    ai_portfolio_event_id: uuid.UUID | None = None,
) -> ClosedPosition:
    """Record a closed position, deriving realized P&L, return, and holding days.

    ``quantity`` is signed: positive for a long, negative for a short. Return is
    derived over the absolute cost basis so the sign stays correct for both.
    ``ai_portfolio_event_id`` links the closure to the AI run that produced it.
    """
    realized_pnl = (exit_price - entry_price) * quantity
    cost_basis = entry_price * abs(quantity)
    return_pct = realized_pnl / cost_basis if cost_basis > 0 else 0.0
    holding_days = (exit_date - entry_date).days

    position = ClosedPosition(
        session_id=session_id,
        ai_portfolio_event_id=ai_portfolio_event_id,
        ticker=ticker,
        quantity=quantity,
        entry_price=entry_price,
        exit_price=exit_price,
        entry_date=entry_date,
        exit_date=exit_date,
        realized_pnl=realized_pnl,
        return_pct=return_pct,
        holding_days=holding_days,
    )
    session.add(position)
    session.commit()
    session.refresh(position)
    return position


def get_closed_positions(
    session: Session,
    session_id: uuid.UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[ClosedPosition]:
    """Return a session's closed positions, most recently exited first.

    Paginated via ``limit``/``offset`` (pair with :func:`count_closed_positions`).
    """
    stmt = (
        select(ClosedPosition)
        .where(ClosedPosition.session_id == session_id)
        .order_by(ClosedPosition.exit_date.desc(), ClosedPosition.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars())


def list_closed_position_pnls(session: Session, session_id: uuid.UUID) -> list[float]:
    """Return every closed position's realised P&L for a session (unbounded)."""
    stmt = select(ClosedPosition.realized_pnl).where(
        ClosedPosition.session_id == session_id
    )
    return list(session.execute(stmt).scalars())


def count_closed_positions(session: Session, session_id: uuid.UUID) -> int:
    """Count a session's closed positions."""
    stmt = (
        select(func.count())
        .select_from(ClosedPosition)
        .where(ClosedPosition.session_id == session_id)
    )
    return session.execute(stmt).scalar_one()


def get_trades_by_event(
    session: Session, event_id: uuid.UUID
) -> list[PaperTrade]:
    """Return the trades an AI run opened (earliest first, as executed)."""
    stmt = (
        select(PaperTrade)
        .where(PaperTrade.ai_portfolio_event_id == event_id)
        .order_by(PaperTrade.executed_at.asc(), PaperTrade.id.asc())
    )
    return list(session.execute(stmt).scalars())


def get_closed_positions_by_event(
    session: Session, event_id: uuid.UUID
) -> list[ClosedPosition]:
    """Return the positions an AI run closed (earliest exit first)."""
    stmt = (
        select(ClosedPosition)
        .where(ClosedPosition.ai_portfolio_event_id == event_id)
        .order_by(ClosedPosition.exit_date.asc(), ClosedPosition.id.asc())
    )
    return list(session.execute(stmt).scalars())


# --------------------------------------------------------------------------- #
# Open-position ledger
# --------------------------------------------------------------------------- #


def get_open_position(
    session: Session, session_id: uuid.UUID, ticker: str
) -> SessionPosition | None:
    """Return the session's open ledger entry for ``ticker`` or ``None`` if flat."""
    stmt = select(SessionPosition).where(
        SessionPosition.session_id == session_id,
        SessionPosition.ticker == ticker,
    )
    return session.execute(stmt).scalars().first()


def list_open_positions(
    session: Session, session_id: uuid.UUID
) -> list[SessionPosition]:
    """Return the session's open ledger entries, in ticker order."""
    stmt = (
        select(SessionPosition)
        .where(SessionPosition.session_id == session_id)
        .order_by(SessionPosition.ticker.asc())
    )
    return list(session.execute(stmt).scalars())


def get_position_entry_basis(
    session: Session, session_id: uuid.UUID, ticker: str
) -> tuple[float, datetime] | None:
    """Return an open position's ``(avg_cost, opened_at)`` entry basis, or ``None``.

    Read *before* a sell fill decrements the ledger so realized P&L uses the
    weighted-average cost and original opened date of the position being exited.
    """
    entry = get_open_position(session, session_id, ticker)
    if entry is None:
        return None
    return entry.avg_cost, entry.opened_at


def apply_fill_to_ledger(
    session: Session,
    *,
    session_id: uuid.UUID,
    ticker: str,
    side: OrderSide,
    shares: float,
    price: float,
) -> SessionPosition | None:
    """Apply one executed fill to the session's open-position ledger.

    A buy opens a new entry or increases an existing one's quantity and re-computes
    its weighted-average cost from ``price`` (``(q*avg + s*price)/(q+s)``). A sell
    reduces the entry's quantity and removes the row once fully exited (remaining
    quantity ``<= LEDGER_QUANTITY_EPSILON``). Returns the updated entry, or ``None``
    when the fill closed (removed) the position or reduced one that was not open.
    """
    entry = get_open_position(session, session_id, ticker)

    if side == OrderSide.BUY:
        if entry is None:
            entry = SessionPosition(
                session_id=session_id,
                ticker=ticker,
                quantity=shares,
                avg_cost=price,
                opened_at=datetime.now(tz=UTC),
            )
            session.add(entry)
        else:
            total = entry.quantity + shares
            entry.avg_cost = (
                (entry.quantity * entry.avg_cost + shares * price) / total
                if total > 0
                else 0.0
            )
            entry.quantity = total
        session.commit()
        session.refresh(entry)
        return entry

    # Sell: reduce and delete on full exit. A sell with no open entry is a no-op.
    if entry is None:
        return None
    entry.quantity -= shares
    if entry.quantity <= LEDGER_QUANTITY_EPSILON:
        session.delete(entry)
        session.commit()
        return None
    session.commit()
    session.refresh(entry)
    return entry


# --------------------------------------------------------------------------- #
# Stop-loss cooldown quarantine
# --------------------------------------------------------------------------- #


def add_stop_loss_quarantine(
    session: Session,
    *,
    session_id: uuid.UUID,
    ticker: str,
    excluded_until: datetime,
) -> StopLossQuarantine:
    """Record a cooldown quarantine keeping ``ticker`` out of rebalances.

    Written on each stop-out; ``excluded_until`` is the moment the cooldown lapses.
    Rows accumulate (one per stop-out) — the rebalance exclusion only checks whether
    any unexpired row exists for the ``(session, ticker)`` pair.
    """
    row = StopLossQuarantine(
        session_id=session_id,
        ticker=ticker,
        excluded_until=excluded_until,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_active_quarantined_tickers(
    session: Session,
    session_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> set[str]:
    """Return the tickers currently under an unexpired stop-loss quarantine.

    A ticker is quarantined while any of its rows has ``excluded_until`` strictly in
    the future relative to ``now`` (defaults to the current time).
    """
    moment = now or datetime.now(tz=UTC)
    stmt = select(StopLossQuarantine.ticker).where(
        StopLossQuarantine.session_id == session_id,
        StopLossQuarantine.excluded_until > moment,
    )
    return set(session.execute(stmt).scalars())


# --------------------------------------------------------------------------- #
# Order-status reconciliation
# --------------------------------------------------------------------------- #


def list_nonterminal_trades(
    session: Session, session_id: uuid.UUID
) -> list[PaperTrade]:
    """Return a session's trades that carry a broker order id and are not terminal.

    These are the trades reconciliation re-queries: they were submitted to the
    broker (``order_id`` present) but their recorded ``order_status`` has not yet
    reached a terminal value, so their fill state may still change.
    """
    stmt = (
        select(PaperTrade)
        .where(
            PaperTrade.session_id == session_id,
            PaperTrade.order_id.is_not(None),
            PaperTrade.order_status.not_in(TERMINAL_ORDER_STATUSES),
        )
        .order_by(PaperTrade.executed_at.asc(), PaperTrade.id.asc())
    )
    return list(session.execute(stmt).scalars())


def adjust_ledger_cost_basis(
    session: Session,
    *,
    session_id: uuid.UUID,
    ticker: str,
    trade_qty: float,
    delta_price: float,
) -> SessionPosition | None:
    """Shift an open position's ``avg_cost`` by a per-share fill-price correction.

    Applies ``new_avg = old_avg + (delta_price * trade_qty) / position_qty`` to the
    ticker's open ledger entry, where ``delta_price`` is the difference between the
    actual and previously recorded fill price of a reconciled buy of ``trade_qty``
    shares. Spreads the correction over the position's *current* remaining quantity
    (which may be less than ``trade_qty`` if some was already sold — an accepted
    approximation). No-op returning ``None`` when the position is no longer open.
    """
    entry = get_open_position(session, session_id, ticker)
    if entry is None or entry.quantity <= 0:
        return None
    entry.avg_cost = entry.avg_cost + (delta_price * trade_qty) / entry.quantity
    session.commit()
    session.refresh(entry)
    return entry


@dataclass
class ReconcileResult:
    """Counts from reconciling one session's non-terminal orders.

    ``trades_seen`` is how many non-terminal trades were examined,
    ``trades_reconciled`` how many the broker returned an order for (and were
    updated), ``trades_filled`` how many of those reached ``filled``, and
    ``trades_basis_corrected`` how many buys shifted the ledger cost basis.
    """

    trades_seen: int = 0
    trades_reconciled: int = 0
    trades_filled: int = 0
    trades_basis_corrected: int = 0


def reconcile_session_orders(
    session: Session,
    broker: Broker,
    session_id: uuid.UUID,
) -> ReconcileResult:
    """Reconcile a session's non-terminal trades against the broker.

    For each trade with a broker order id whose recorded status is not terminal,
    re-fetches the order (``broker.get_order``) and updates the trade's
    ``order_status`` / ``filled_price`` / ``filled_at`` to the broker's current
    values. When a *buy* fills at a price different from the one recorded at
    submission, the open-position cost basis for that ticker is corrected via
    :func:`adjust_ledger_cost_basis`. A broker error or an unknown order (``None``)
    leaves that trade untouched and the batch continues, so a transient failure
    never corrupts recorded data.

    Raises :class:`SessionNotFoundError` for an unknown session.
    """
    get_session(session, session_id)  # 404 for an unknown session.
    trades = list_nonterminal_trades(session, session_id)
    result = ReconcileResult(trades_seen=len(trades))

    for trade in trades:
        if trade.order_id is None:
            continue
        try:
            order = broker.get_order(trade.order_id)
        except Exception as exc:  # noqa: BLE001 - one bad order can't abort the batch
            logger.warning(
                "reconcile: get_order failed for trade %s (order %s): %s",
                trade.id,
                trade.order_id,
                exc,
            )
            continue
        if order is None:
            continue

        # Effective old price, captured before mutating: the last fill estimate.
        old_price = trade.filled_price if trade.filled_price is not None else trade.price

        trade.order_status = order.status.value
        if order.filled_price is not None:
            trade.filled_price = order.filled_price
        if order.filled_at is not None:
            trade.filled_at = order.filled_at
        session.commit()
        session.refresh(trade)
        result.trades_reconciled += 1
        if trade.order_status == OrderStatus.FILLED.value:
            result.trades_filled += 1

        if (
            trade.side == OrderSide.BUY.value
            and order.filled_price is not None
            and order.filled_price != old_price
        ):
            corrected = adjust_ledger_cost_basis(
                session,
                session_id=session_id,
                ticker=trade.ticker,
                trade_qty=trade.quantity,
                delta_price=order.filled_price - old_price,
            )
            if corrected is not None:
                result.trades_basis_corrected += 1

    return result


# --------------------------------------------------------------------------- #
# Portfolio-value snapshots
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SessionValuation:
    """A session's mark-to-market equity at a point in time.

    ``total_value`` is the session's equity (``allocated_capital + realized
    total_pnl + unrealized P&L`` of the ledger positions); ``positions_value`` is
    the market value of the held positions and ``cash_value`` the remainder.
    ``unrealized_pnl`` is the summed mark-to-market gain/loss on the open
    positions. ``positions`` is the per-holding breakdown persisted on the
    snapshot.
    """

    total_value: float
    cash_value: float
    positions_value: float
    unrealized_pnl: float
    positions: list[dict[str, Any]]


def compute_session_value(
    session: Session,
    *,
    session_id: uuid.UUID,
    broker: Broker,
) -> SessionValuation:
    """Value a session by marking its ledger positions to market.

    ``total_value = allocated_capital + realized total_pnl − total_fees +
    Σ(market_value − cost_basis)`` over the session's open ledger positions, where
    ``market_value`` is priced from ``broker.get_quotes`` and ``total_fees`` is the
    cumulative per-trade transaction cost. A position whose quote can't be fetched
    (missing symbol or a quote with no usable price) is valued at its ledger
    ``avg_cost`` and the gap logged, so one bad quote never sinks the snapshot. A
    session with no open positions yields an all-cash valuation.
    """
    session_row = get_session(session, session_id)
    ledger = list_open_positions(session, session_id)

    quotes: dict[str, Any] = {}
    tickers = [entry.ticker for entry in ledger]
    if tickers:
        try:
            quotes = broker.get_quotes(tickers)
        except Exception as exc:  # noqa: BLE001 - pricing is best-effort
            logger.warning(
                "snapshot: quote fetch failed for session %s: %s", session_id, exc
            )
            quotes = {}

    positions: list[dict[str, Any]] = []
    positions_value = 0.0
    unrealized_total = 0.0
    for entry in ledger:
        cost = entry.avg_cost or 0.0
        cost_basis = entry.quantity * cost
        price = quote_price(quotes.get(entry.ticker))
        if price is None:
            logger.warning(
                "snapshot: no quote for %s (session %s); valuing at avg cost",
                entry.ticker,
                session_id,
            )
            price = cost
        market_value = entry.quantity * price
        unrealized = market_value - cost_basis
        positions_value += market_value
        unrealized_total += unrealized
        positions.append(
            {
                "ticker": entry.ticker,
                "quantity": entry.quantity,
                "price": price,
                "market_value": market_value,
                "unrealized_pnl": unrealized,
                "return_pct": (price / cost - 1.0) if cost > 0 else 0.0,
            }
        )

    total_value = (
        session_row.allocated_capital
        + session_row.total_pnl
        - session_row.total_fees
        + unrealized_total
    )
    cash_value = total_value - positions_value
    return SessionValuation(
        total_value=total_value,
        cash_value=cash_value,
        positions_value=positions_value,
        unrealized_pnl=unrealized_total,
        positions=positions,
    )


# --------------------------------------------------------------------------- #
# Sector / category performance attribution
# --------------------------------------------------------------------------- #

# Sentinel group keys (mirror the dashboard's NO_SECTOR_KEY convention): a held
# asset with no sector lands in "No sector" (by-sector only); a position ticker
# that no longer matches any catalogue asset lands in "Unknown" (both groupings),
# so no P&L is ever silently dropped.
NO_SECTOR_GROUP_KEY = "No sector"
UNKNOWN_GROUP_KEY = "Unknown"


@dataclass(frozen=True)
class GroupPerformance:
    """Performance attribution for one sector/category group within a session."""

    key: str
    market_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    return_pct: float | None


@dataclass(frozen=True)
class SessionSectorPerformance:
    """A session's P&L attributed to sectors and categories."""

    by_sector: list[GroupPerformance]
    by_category: list[GroupPerformance]


@dataclass
class _GroupAccumulator:
    """Mutable running totals for one group while aggregating."""

    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    market_value: float = 0.0
    cost_basis: float = 0.0


def session_sector_performance(
    session: Session,
    *,
    session_id: uuid.UUID,
    broker: Broker,
) -> SessionSectorPerformance:
    """Attribute a session's realised + unrealised P&L to sectors and categories.

    Marks the session's open positions to market via :func:`compute_session_value`,
    sums each closed position's realised P&L, and joins both to the asset catalogue
    on a normalised ticker to group by ``Asset.sector`` and ``Asset.category``. Each
    group reports realised, unrealised and total P&L, open-position market value, and
    a return fraction (``total_pnl / cost_basis``, ``None`` when the cost basis is
    zero). A null sector buckets under :data:`NO_SECTOR_GROUP_KEY` (by sector only);
    a ticker with no matching asset buckets under :data:`UNKNOWN_GROUP_KEY` (both
    groupings), so every unit of P&L is attributed. Raises
    :class:`SessionNotFoundError` for an unknown session.
    """
    get_session(session, session_id)  # 404 on unknown session.

    valuation = compute_session_value(session, session_id=session_id, broker=broker)
    closed = list(
        session.execute(
            select(ClosedPosition).where(ClosedPosition.session_id == session_id)
        ).scalars()
    )

    # Resolve the sector/category of every ticker involved in one catalogue query.
    tickers = {normalize_ticker(pos["ticker"]) for pos in valuation.positions}
    tickers |= {normalize_ticker(cp.ticker) for cp in closed}
    catalogue: dict[str, tuple[str, str | None]] = {}
    if tickers:
        rows = session.execute(
            select(Asset.ticker, Asset.category, Asset.sector).where(
                Asset.ticker.in_(tickers)
            )
        ).all()
        catalogue = {row[0]: (row[1], row[2]) for row in rows}

    by_sector: dict[str, _GroupAccumulator] = {}
    by_category: dict[str, _GroupAccumulator] = {}

    def _keys(ticker: str) -> tuple[str, str]:
        """Return the (sector_key, category_key) group keys for a ticker."""
        entry = catalogue.get(normalize_ticker(ticker))
        if entry is None:
            return UNKNOWN_GROUP_KEY, UNKNOWN_GROUP_KEY
        category, sector = entry
        return (sector or NO_SECTOR_GROUP_KEY), category

    for pos in valuation.positions:
        sector_key, category_key = _keys(pos["ticker"])
        market_value = pos["market_value"]
        unrealized = pos["unrealized_pnl"]
        cost_basis = market_value - unrealized
        for grouping, key in ((by_sector, sector_key), (by_category, category_key)):
            acc = grouping.setdefault(key, _GroupAccumulator())
            acc.unrealized_pnl += unrealized
            acc.market_value += market_value
            acc.cost_basis += cost_basis

    for cp in closed:
        sector_key, category_key = _keys(cp.ticker)
        cost_basis = abs(cp.entry_price * cp.quantity)
        for grouping, key in ((by_sector, sector_key), (by_category, category_key)):
            acc = grouping.setdefault(key, _GroupAccumulator())
            acc.realized_pnl += cp.realized_pnl
            acc.cost_basis += cost_basis

    return SessionSectorPerformance(
        by_sector=_finalize_groups(by_sector),
        by_category=_finalize_groups(by_category),
    )


def _finalize_groups(
    groups: dict[str, _GroupAccumulator],
) -> list[GroupPerformance]:
    """Convert accumulators to immutable rows, most profitable first.

    The per-group return is ``total_pnl / cost_basis``; a zero cost basis yields
    ``None`` (unavailable) rather than a divide-by-zero.
    """
    rows = [
        GroupPerformance(
            key=key,
            market_value=acc.market_value,
            realized_pnl=acc.realized_pnl,
            unrealized_pnl=acc.unrealized_pnl,
            total_pnl=acc.realized_pnl + acc.unrealized_pnl,
            return_pct=(
                (acc.realized_pnl + acc.unrealized_pnl) / acc.cost_basis
                if acc.cost_basis != 0
                else None
            ),
        )
        for key, acc in groups.items()
    ]
    rows.sort(key=lambda row: (-row.total_pnl, row.key))
    return rows


def quote_price(quote: Any) -> float | None:
    """Extract a usable price from a broker :class:`Quote`, or ``None``.

    Prefers the midpoint (which itself falls back to the last trade), then the
    ask. Returns ``None`` when the quote is absent or carries no price at all, so
    the caller can fall back to the ledger cost basis. Shared by the value-snapshot
    job and the stop-loss scan so both mark positions the same way.
    """
    if quote is None:
        return None
    price = getattr(quote, "mid", None)
    if price is None:
        price = getattr(quote, "ask", None)
    return price


def record_value_snapshot(
    session: Session,
    *,
    session_id: uuid.UUID,
    as_of: date,
    broker: Broker,
) -> SessionValueSnapshot:
    """Upsert the session's value snapshot for ``as_of`` and return it.

    Idempotent per ``(session_id, snapshot_date)``: an existing row for that day is
    updated in place, otherwise a new one is inserted. ``daily_pnl`` is measured
    against the most recent *prior* snapshot's ``total_value`` (or the session's
    ``allocated_capital`` when none exists), *minus* any capital contributed on
    ``as_of`` so an added deposit is not reported as a gain; ``daily_pnl_pct``
    divides by that baseline, guarding against a non-positive baseline.
    """
    session_row = get_session(session, session_id)
    valuation = compute_session_value(session, session_id=session_id, broker=broker)

    # Capital contributed during this snapshot's period lifts total_value but is not a
    # gain, so net it out of the day's P&L. The baseline is the prior snapshot's value
    # (which already reflects earlier contributions) or, for the first snapshot, the
    # original inception capital (allocated_capital minus every recorded contribution).
    events = list_capital_events(session, session_id=session_id)
    prior = _prior_snapshot(session, session_id, as_of)
    if prior is not None:
        baseline = prior.total_value
        contributed = sum(
            event.amount
            for event in events
            if prior.snapshot_date < event.effective_date <= as_of
        )
    else:
        baseline = session_row.allocated_capital - sum(e.amount for e in events)
        contributed = sum(
            event.amount for event in events if event.effective_date <= as_of
        )
    daily_pnl = valuation.total_value - contributed - baseline
    daily_pnl_pct = daily_pnl / baseline if baseline > 0 else 0.0

    row = _get_snapshot(session, session_id, as_of)
    if row is None:
        row = SessionValueSnapshot(session_id=session_id, snapshot_date=as_of)
        session.add(row)
    row.total_value = valuation.total_value
    row.cash_value = valuation.cash_value
    row.positions_value = valuation.positions_value
    row.daily_pnl = daily_pnl
    row.daily_pnl_pct = daily_pnl_pct
    row.positions = valuation.positions
    session.commit()
    session.refresh(row)
    return row


def _get_snapshot(
    session: Session, session_id: uuid.UUID, snapshot_date: date
) -> SessionValueSnapshot | None:
    """Return the session's snapshot for ``snapshot_date`` or ``None``."""
    stmt = select(SessionValueSnapshot).where(
        SessionValueSnapshot.session_id == session_id,
        SessionValueSnapshot.snapshot_date == snapshot_date,
    )
    return session.execute(stmt).scalars().first()


def _prior_snapshot(
    session: Session, session_id: uuid.UUID, before: date
) -> SessionValueSnapshot | None:
    """Return the session's most recent snapshot strictly before ``before``."""
    stmt = (
        select(SessionValueSnapshot)
        .where(
            SessionValueSnapshot.session_id == session_id,
            SessionValueSnapshot.snapshot_date < before,
        )
        .order_by(SessionValueSnapshot.snapshot_date.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


def list_value_snapshots(
    session: Session, *, session_id: uuid.UUID
) -> list[SessionValueSnapshot]:
    """Return the session's value snapshots ordered oldest date first."""
    stmt = (
        select(SessionValueSnapshot)
        .where(SessionValueSnapshot.session_id == session_id)
        .order_by(SessionValueSnapshot.snapshot_date.asc())
    )
    return list(session.execute(stmt).scalars())


def get_value_snapshot(
    session: Session, *, session_id: uuid.UUID, snapshot_date: date
) -> SessionValueSnapshot | None:
    """Return the session's value snapshot for ``snapshot_date`` or ``None``."""
    return _get_snapshot(session, session_id, snapshot_date)


def get_daily_run_snapshot(
    session: Session, *, session_id: uuid.UUID, run_date: date
) -> SessionDailyRunSnapshot | None:
    """Return the session's consolidated learning snapshot for ``run_date`` or ``None``."""
    stmt = select(SessionDailyRunSnapshot).where(
        SessionDailyRunSnapshot.session_id == session_id,
        SessionDailyRunSnapshot.run_date == run_date,
    )
    return session.execute(stmt).scalars().first()


def list_daily_run_snapshots(
    session: Session, *, session_id: uuid.UUID, limit: int
) -> list[SessionDailyRunSnapshot]:
    """Return the session's most recent consolidated learning snapshots, newest first.

    Ordered by ``run_date`` descending and capped at ``limit`` (``<= 0`` returns an
    empty list). Read-only; used to feed the rebalance agent a short, recent window of
    its own prior daily-run outcomes when learning feedback is enabled.
    """
    if limit <= 0:
        return []
    stmt = (
        select(SessionDailyRunSnapshot)
        .where(SessionDailyRunSnapshot.session_id == session_id)
        .order_by(SessionDailyRunSnapshot.run_date.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


def record_daily_run_snapshot(
    session: Session,
    *,
    session_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    run_date: date,
    ai_portfolio_event_id: uuid.UUID | None,
    document: dict[str, Any],
) -> SessionDailyRunSnapshot:
    """Upsert the session's consolidated daily-run learning snapshot for ``run_date``.

    Idempotent per ``(session_id, run_date)``: an existing row for that day is updated
    in place (so re-running the assembly reflects the latest reconciled data rather
    than duplicating), otherwise a new one is inserted. Backend-only — never exposed
    through a read schema or API.
    """
    row = get_daily_run_snapshot(session, session_id=session_id, run_date=run_date)
    if row is None:
        row = SessionDailyRunSnapshot(session_id=session_id, run_date=run_date)
        session.add(row)
    row.portfolio_id = portfolio_id
    row.ai_portfolio_event_id = ai_portfolio_event_id
    row.document = document
    session.commit()
    session.refresh(row)
    return row


def list_capital_events(
    session: Session, *, session_id: uuid.UUID
) -> list[SessionCapitalEvent]:
    """Return the session's capital-contribution events, oldest effective-date first."""
    stmt = (
        select(SessionCapitalEvent)
        .where(SessionCapitalEvent.session_id == session_id)
        .order_by(
            SessionCapitalEvent.effective_date.asc(),
            SessionCapitalEvent.created_at.asc(),
        )
    )
    return list(session.execute(stmt).scalars())


def session_contributions(
    session_row: PaperTradingSession,
    events: Sequence[SessionCapitalEvent],
    *,
    start_date: date,
) -> list[Contribution]:
    """Derive a session's ordered contribution set from its baseline and events.

    Returns ``{(start_date, allocated_capital − Σ event.amount)}`` followed by one
    ``(effective_date, amount)`` per event (ascending by effective date). The
    synthetic first element is the original build capital treated as a contribution
    on ``start_date``; a session with no events yields a single baseline equal to
    ``allocated_capital`` — so every contribution-aware formula collapses to the
    pre-increase behavior. No data backfill is needed.
    """
    ordered = sorted(events, key=lambda e: (e.effective_date, e.created_at))
    baseline_amount = session_row.allocated_capital - sum(e.amount for e in ordered)
    contributions = [Contribution(effective_date=start_date, amount=baseline_amount)]
    contributions.extend(
        Contribution(effective_date=e.effective_date, amount=e.amount)
        for e in ordered
    )
    return contributions


def contribution_adjusted_returns(
    snapshots: Sequence[SessionValueSnapshot],
    contributions: Sequence[Contribution],
) -> list[float]:
    """Per-snapshot, contribution-adjusted daily returns ``r_d``.

    For each snapshot day ``d`` with NAV ``V_d`` and same-period contributions
    ``C_d``, ``r_d = (V_d − C_d − V_{d−1}) / V_{d−1}``, where ``V_{d−1}`` is the prior
    snapshot's NAV and, for the first snapshot, the baseline contributed capital
    (``contributions[0].amount``). Each event is attributed to the first snapshot
    period whose date is on or after its effective date, so a contribution is never
    counted as a gain. A non-positive prior value contributes a ``0.0`` return rather
    than dividing by zero. Without contributions this reduces exactly to the stored
    daily return series.
    """
    if not snapshots:
        return []
    baseline = contributions[0].amount
    events = contributions[1:]
    series: list[float] = []
    prev_value = baseline
    prev_date: date | None = None
    for snap in snapshots:
        if prev_date is None:
            contributed = sum(
                c.amount for c in events if c.effective_date <= snap.snapshot_date
            )
        else:
            contributed = sum(
                c.amount
                for c in events
                if prev_date < c.effective_date <= snap.snapshot_date
            )
        if prev_value > 0:
            series.append((snap.total_value - contributed - prev_value) / prev_value)
        else:
            series.append(0.0)
        prev_value = snap.total_value
        prev_date = snap.snapshot_date
    return series


def time_weighted_return(
    snapshots: Sequence[SessionValueSnapshot],
    contributions: Sequence[Contribution],
    *,
    live_value: float,
    as_of: date,
) -> float:
    """Chained time-weighted return of the contribution-adjusted daily series.

    Chains the per-snapshot returns from :func:`contribution_adjusted_returns` and a
    final live sub-period (from the last snapshot — or the baseline when there are no
    snapshots — to ``live_value`` at ``as_of``), excluding any contribution effective
    in that final period. Returns ``Π(1 + r) − 1``. Without contributions this
    telescopes to the simple return ``(live_value − allocated_capital) /
    allocated_capital``.
    """
    series = list(contribution_adjusted_returns(snapshots, contributions))
    events = contributions[1:]
    if snapshots:
        last = snapshots[-1]
        contributed = sum(
            c.amount
            for c in events
            if last.snapshot_date < c.effective_date <= as_of
        )
        if last.total_value > 0:
            series.append(
                (live_value - contributed - last.total_value) / last.total_value
            )
    else:
        baseline = contributions[0].amount
        contributed = sum(c.amount for c in events if c.effective_date <= as_of)
        if baseline > 0:
            series.append((live_value - contributed - baseline) / baseline)
    growth = 1.0
    for r in series:
        growth *= 1.0 + r
    return growth - 1.0


def _growth_index(returns: Sequence[float]) -> list[float]:
    """Cumulative growth index ``g_d = Π_{i≤d}(1 + r_i)`` of a return series.

    Used for a contribution-aware max-drawdown: a deposit does not look like a jump
    or a recovery because the index tracks compounded return, not raw NAV.
    """
    index: list[float] = []
    growth = 1.0
    for r in returns:
        growth *= 1.0 + r
        index.append(growth)
    return index


@dataclass(frozen=True)
class ValueHistoryPoint:
    """A value snapshot paired with the session's benchmark value for its date.

    ``benchmark_value`` is a buy-and-hold of the session's contributed capital in the
    session's benchmark: each contribution buys units at its effective date's close,
    so the line receives the same cash the session did and steps up on a contribution
    date. ``None`` when the benchmark has no stored price on or before the snapshot's
    date.
    """

    snapshot: SessionValueSnapshot
    benchmark_value: float | None


def list_value_history(
    session: Session, *, session_id: uuid.UUID
) -> list[ValueHistoryPoint]:
    """Return the session's value snapshots (oldest first) with benchmark values.

    Each snapshot carries the rebased benchmark value for its date, derived from the
    stored benchmark price series (rebased to the session's first snapshot date and
    allocated capital). A snapshot whose date precedes the benchmark's first stored
    close (or when no prices are stored) carries a ``None`` benchmark value.

    Raises :class:`SessionNotFoundError` for an unknown session.
    """
    session_row = get_session(session, session_id)
    snapshots = list_value_snapshots(session, session_id=session_id)
    if not snapshots:
        return []

    series = load_benchmark_series(session, session_row.benchmark)
    start_date = snapshots[0].snapshot_date
    events = list_capital_events(session, session_id=session_id)
    contributions = session_contributions(
        session_row, events, start_date=start_date
    )
    return [
        ValueHistoryPoint(
            snapshot=snap,
            benchmark_value=rebased_benchmark_value(
                series,
                contributions=contributions,
                as_of=snap.snapshot_date,
            ),
        )
        for snap in snapshots
    ]


@dataclass(frozen=True)
class SessionComparisonPoint:
    """A single (date, value) point of a session's value history for comparison."""

    snapshot_date: date
    total_value: float


@dataclass(frozen=True)
class SessionComparisonSeries:
    """One session's value series for the multi-session comparison read.

    ``label`` is the session's portfolio name, falling back to its strategy key
    when no portfolio name resolves. ``points`` is ordered oldest date first and is
    empty when the session has no snapshots yet.
    """

    session_id: uuid.UUID
    label: str
    allocated_capital: float
    points: list[SessionComparisonPoint]


def list_sessions_value_comparison(
    session: Session,
) -> list[SessionComparisonSeries]:
    """Return every non-archived session with its value points, for comparison.

    Reuses the default (non-archived) session listing for membership and each
    session's ordered value snapshots for points, so archived sessions are excluded
    and a session with no snapshots is returned with an empty points list.
    """
    return [
        SessionComparisonSeries(
            session_id=row.id,
            label=row.portfolio_name or row.strategy_key,
            allocated_capital=row.allocated_capital,
            points=[
                SessionComparisonPoint(
                    snapshot_date=snap.snapshot_date,
                    total_value=snap.total_value,
                )
                for snap in list_value_snapshots(session, session_id=row.id)
            ],
        )
        for row in list_sessions(session, include_archived=False)
    ]


# --------------------------------------------------------------------------- #
# Session KPIs (live valuation + Sharpe)
# --------------------------------------------------------------------------- #


def sharpe_ratio(
    returns: Sequence[float], *, risk_free: float = 0.0
) -> float | None:
    """Annualised Sharpe ratio of a per-period return series, or ``None``.

    ``returns`` are per-period (daily) fractional returns; ``risk_free`` is the
    per-period risk-free rate subtracted from each. The ratio is
    ``mean(excess) / stdev(returns) × √SHARPE_TRADING_DAYS_PER_YEAR`` using the
    sample standard deviation. Returns ``None`` when there are fewer than
    :data:`SHARPE_MIN_RETURNS` observations or the returns have zero standard
    deviation (a flat series has no risk-adjusted signal and would divide by
    zero).
    """
    if len(returns) < SHARPE_MIN_RETURNS:
        return None
    stdev = statistics.stdev(returns)
    if stdev == 0:
        return None
    mean_excess = statistics.fmean(returns) - risk_free
    return float(mean_excess / stdev * (SHARPE_TRADING_DAYS_PER_YEAR**0.5))


def max_drawdown(values: Sequence[float]) -> float | None:
    """Largest peak-to-trough decline over a date-ordered value series.

    Returns the deepest drop below a running peak as a non-negative fraction of
    that peak, ``0.0`` for a series that never falls below a prior peak, and
    ``None`` for an empty series. A non-positive running peak contributes no
    drawdown (guards the division).
    """
    if not values:
        return None
    peak = values[0]
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            drop = (peak - value) / peak
            max_dd = max(max_dd, drop)
    return max_dd


@dataclass(frozen=True)
class ClosedPositionStats:
    """Win-rate and trade-quality figures over closed-position realised P&L.

    ``win_rate`` is the fraction of positions with P&L > 0 (over all positions);
    ``average_win``/``average_loss`` the mean of the strictly-positive/negative
    subsets; ``best_trade``/``worst_trade`` the max/min P&L. Each field is
    ``None`` when its input is empty — all ``None`` with no positions, and a
    win/loss average ``None`` when that side has no members.
    """

    win_rate: float | None
    average_win: float | None
    average_loss: float | None
    best_trade: float | None
    worst_trade: float | None


def closed_position_stats(pnls: Sequence[float]) -> ClosedPositionStats:
    """Compute :class:`ClosedPositionStats` from closed-position realised P&L."""
    if not pnls:
        return ClosedPositionStats(None, None, None, None, None)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    return ClosedPositionStats(
        win_rate=len(wins) / len(pnls),
        average_win=statistics.fmean(wins) if wins else None,
        average_loss=statistics.fmean(losses) if losses else None,
        best_trade=max(pnls),
        worst_trade=min(pnls),
    )


@dataclass(frozen=True)
class SessionKpis:
    """A session's headline performance KPIs at request time.

    ``current_value`` is the live net asset value (net of fees);
    ``unallocated_cash`` the portion of that value currently held as cash (the live
    value minus the marked-to-market positions value); ``realised_pnl``
    the session's cumulative gross realised P&L; ``unrealised_pnl`` the live
    mark-to-market on open positions; ``total_fees`` the cumulative
    transaction cost charged to date; ``daily_avg_orders`` the number of recorded
    orders (trades) divided by the number of recorded daily value snapshots
    (``None`` until the session has at least one snapshot); ``total_return`` the
    absolute gain/loss versus
    total contributed capital (``current_value − allocated_capital``) and
    ``total_return_pct`` the *time-weighted* fractional return (the chained
    contribution-adjusted daily series, so a mid-session capital increase is not
    counted as a gain; equal to the simple return when there are no contributions);
    ``sharpe_ratio`` the annualised Sharpe of the contribution-adjusted daily return
    series, or ``None`` until enough history exists. ``benchmark`` is the session's
    benchmark id;
    ``benchmark_return_pct`` the benchmark's buy-and-hold fractional return over the
    session's period and ``excess_return_pct`` the session's total-return fraction
    minus it; ``excess_return`` is that excess as an absolute amount
    (``excess_return_pct × allocated_capital``) — the session's net-of-fees dollar
    gain minus what a costless buy-and-hold of the benchmark would have gained on the
    same capital. All three are ``None`` when the benchmark has insufficient stored
    prices.

    ``max_drawdown`` is the largest peak-to-trough decline of the session's
    cumulative growth index (the compounded contribution-adjusted daily returns) as a
    non-negative fraction (``None`` without snapshots). ``win_rate`` is the
    fraction of closed positions with realised P&L > 0; ``average_win`` and
    ``average_loss`` the mean realised P&L of the winning/losing closed positions;
    ``best_trade`` and ``worst_trade`` the max/min realised P&L. The trade figures
    are ``None`` when the session has no closed positions, and the win/loss average
    is ``None`` when that side has no members.
    """

    current_value: float
    unallocated_cash: float
    realised_pnl: float
    unrealised_pnl: float
    total_fees: float
    daily_avg_orders: float | None
    total_return: float
    total_return_pct: float
    sharpe_ratio: float | None
    benchmark: str
    benchmark_return_pct: float | None
    excess_return_pct: float | None
    excess_return: float | None
    max_drawdown: float | None
    win_rate: float | None
    average_win: float | None
    average_loss: float | None
    best_trade: float | None
    worst_trade: float | None


def session_kpis(
    session: Session,
    *,
    session_id: uuid.UUID,
    broker: Broker,
) -> SessionKpis:
    """Compute a session's live performance KPIs (404 via ``SessionNotFoundError``).

    Marks the session's open positions to market via ``broker`` for the live
    figures, reads the cumulative realised P&L from the session row, and derives the
    absolute total return against total contributed capital
    (``allocated_capital``). The fractional total return is *time-weighted*: the
    contribution-adjusted daily return series is chained so a mid-session capital
    increase is not counted as a gain and historical return stays comparable across
    deposits. The Sharpe ratio and max drawdown use that same series (the latter via
    its cumulative growth index). The risk-free rate is the configured annual rate
    converted to a per-day rate. A session with no contributions reduces exactly to
    the simple-return behavior.
    """
    session_row = get_session(session, session_id)
    valuation = compute_session_value(session, session_id=session_id, broker=broker)

    allocated = session_row.allocated_capital
    # Absolute return stays contribution-neutral: allocated_capital is the running
    # total of contributed capital, so current value minus it is the real dollar gain.
    total_return = valuation.total_value - allocated

    snapshots = list_value_snapshots(session, session_id=session_id)
    as_of = datetime.now(tz=UTC).date()
    start_date = snapshots[0].snapshot_date if snapshots else as_of
    events = list_capital_events(session, session_id=session_id)
    contributions = session_contributions(session_row, events, start_date=start_date)

    # Fractional total return is time-weighted over the contribution-adjusted daily
    # series plus a final live leg, so an injected deposit never inflates it.
    total_return_pct = time_weighted_return(
        snapshots, contributions, live_value=valuation.total_value, as_of=as_of
    )
    # Sharpe and drawdown read the same contribution-adjusted daily series (not the
    # raw stored daily_pnl_pct, which was measured against whatever allocated capital
    # existed when each snapshot was written).
    daily_returns = contribution_adjusted_returns(snapshots, contributions)
    daily_risk_free = settings.SHARPE_RISK_FREE_RATE / SHARPE_TRADING_DAYS_PER_YEAR

    # Average orders per snapshot day: the session's recorded trade count spread
    # over the number of recorded daily value snapshots. None until the first
    # snapshot so we never divide by zero.
    daily_avg_orders = (
        count_session_trades(session, session_id) / len(snapshots)
        if snapshots
        else None
    )

    # Benchmark comparison: buy-and-hold return from the session's start (its first
    # snapshot date) to the latest available benchmark close. Unavailable (None)
    # when the session has no snapshots yet or the series lacks a start/end close.
    #
    # The benchmark fraction is intentionally NOT contribution-aware: a benchmark is
    # a single buy-and-hold instrument, so its per-dollar (time-weighted) return
    # over the period is close(latest)/close(start) − 1 regardless of cash flows.
    # Both sides of the excess are therefore time-weighted and comparable. (The
    # value-history dollar overlay, by contrast, IS contribution-aware so the chart
    # line receives the same cash — see rebased_benchmark_value. Do not "unify" them.)
    benchmark_return_pct: float | None = None
    if snapshots:
        series = load_benchmark_series(session, session_row.benchmark)
        benchmark_return_pct = benchmark_return_fraction(
            series,
            start_date=snapshots[0].snapshot_date,
            as_of=as_of,
        )
    excess_return_pct = (
        total_return_pct - benchmark_return_pct
        if benchmark_return_pct is not None
        else None
    )
    # Absolute excess on the session's contributed capital. total_return already nets
    # out per-trade fees while the benchmark leg is a costless buy-and-hold, so this
    # is the session's real net-of-fees dollar gain minus the index's dollar gain.
    excess_return = (
        excess_return_pct * allocated if excess_return_pct is not None else None
    )

    # Drawdown from the cumulative growth index so a contribution is not read as a
    # jump or a recovery (identical to NAV drawdown when there are no contributions).
    drawdown = max_drawdown(_growth_index(daily_returns))
    trade_stats = closed_position_stats(
        list_closed_position_pnls(session, session_id)
    )

    return SessionKpis(
        current_value=valuation.total_value,
        unallocated_cash=valuation.cash_value,
        realised_pnl=session_row.total_pnl,
        unrealised_pnl=valuation.unrealized_pnl,
        total_fees=session_row.total_fees,
        daily_avg_orders=daily_avg_orders,
        total_return=total_return,
        total_return_pct=total_return_pct,
        sharpe_ratio=sharpe_ratio(daily_returns, risk_free=daily_risk_free),
        benchmark=session_row.benchmark,
        benchmark_return_pct=benchmark_return_pct,
        excess_return_pct=excess_return_pct,
        excess_return=excess_return,
        max_drawdown=drawdown,
        win_rate=trade_stats.win_rate,
        average_win=trade_stats.average_win,
        average_loss=trade_stats.average_loss,
        best_trade=trade_stats.best_trade,
        worst_trade=trade_stats.worst_trade,
    )
