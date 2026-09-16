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

from cadence.broker.base import Broker
from cadence.broker.models import OrderSide, OrderStatus
from cadence.config import settings
from cadence.paper_trading.constants import (
    SHARPE_MIN_RETURNS,
    SHARPE_TRADING_DAYS_PER_YEAR,
    TERMINAL_ORDER_STATUSES,
    RunStatus,
    ScheduleMode,
    SessionStatus,
)
from cadence.paper_trading.errors import (
    DuplicateSessionError,
    SessionNotArchivableError,
    SessionNotFoundError,
)
from cadence.paper_trading.models import (
    ClosedPosition,
    PaperTrade,
    PaperTradingSession,
    SessionPosition,
    SessionRun,
    SessionValueSnapshot,
)

logger = logging.getLogger(__name__)

# Default seed capital for a new session (mirrors trading-bot).
DEFAULT_ALLOCATED_CAPITAL = 100000.0

# A ledger position whose remaining quantity falls at or below this is treated as
# fully exited and its row removed. Sized to the executor's crypto quantity
# precision (8 decimals) so fractional dust nets cleanly to a closed position.
LEDGER_QUANTITY_EPSILON = 1e-8


def create_session(
    session: Session,
    *,
    portfolio_id: uuid.UUID,
    strategy_key: str,
    allocated_capital: float = DEFAULT_ALLOCATED_CAPITAL,
    max_allocation_pct: float = 1.0,
    schedule_mode: ScheduleMode = ScheduleMode.SCHEDULED,
) -> PaperTradingSession:
    """Create a paper-trading session for a ``(portfolio, strategy)`` pair.

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
    order_id: str | None = None,
    order_status: OrderStatus = OrderStatus.FILLED,
    filled_price: float | None = None,
    filled_at: datetime | None = None,
    ai_portfolio_event_id: uuid.UUID | None = None,
) -> PaperTrade:
    """Record a paper trade (fill). ``notional`` is derived as ``quantity * price``.

    ``ai_portfolio_event_id`` links the trade to the AI run that produced it; it is
    left NULL for non-AI strategies.
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
    session.commit()
    session.refresh(trade)
    return trade


def get_session_trades(
    session: Session,
    session_id: uuid.UUID,
    *,
    limit: int = 100,
) -> list[PaperTrade]:
    """Return a session's trades, most recent first."""
    stmt = (
        select(PaperTrade)
        .where(PaperTrade.session_id == session_id)
        .order_by(PaperTrade.executed_at.desc(), PaperTrade.id.desc())
        .limit(limit)
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
) -> list[SessionRun]:
    """Return a session's run history, most recent first."""
    stmt = (
        select(SessionRun)
        .where(SessionRun.session_id == session_id)
        .order_by(SessionRun.run_at.desc(), SessionRun.id.desc())
        .limit(limit)
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
) -> list[ClosedPosition]:
    """Return a session's closed positions, most recently exited first."""
    stmt = (
        select(ClosedPosition)
        .where(ClosedPosition.session_id == session_id)
        .order_by(ClosedPosition.exit_date.desc(), ClosedPosition.id.desc())
        .limit(limit)
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

    ``total_value = allocated_capital + realized total_pnl + Σ(market_value −
    cost_basis)`` over the session's open ledger positions, where ``market_value``
    is priced from ``broker.get_quotes``. A position whose quote can't be fetched
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
        price = _quote_price(quotes.get(entry.ticker))
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
        session_row.allocated_capital + session_row.total_pnl + unrealized_total
    )
    cash_value = total_value - positions_value
    return SessionValuation(
        total_value=total_value,
        cash_value=cash_value,
        positions_value=positions_value,
        unrealized_pnl=unrealized_total,
        positions=positions,
    )


def _quote_price(quote: Any) -> float | None:
    """Extract a usable price from a broker :class:`Quote`, or ``None``.

    Prefers the midpoint (which itself falls back to the last trade), then the
    ask. Returns ``None`` when the quote is absent or carries no price at all, so
    the caller can fall back to the ledger cost basis.
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
    ``allocated_capital`` when none exists); ``daily_pnl_pct`` divides by that
    baseline, guarding against a non-positive baseline.
    """
    session_row = get_session(session, session_id)
    valuation = compute_session_value(session, session_id=session_id, broker=broker)

    prior = _prior_snapshot(session, session_id, as_of)
    baseline = prior.total_value if prior is not None else session_row.allocated_capital
    daily_pnl = valuation.total_value - baseline
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


@dataclass(frozen=True)
class SessionKpis:
    """A session's headline performance KPIs at request time.

    ``current_value`` is the live net asset value; ``realised_pnl`` the session's
    cumulative realised P&L; ``unrealised_pnl`` the live mark-to-market on open
    positions; ``total_return`` the absolute gain/loss versus allocated capital
    (``current_value − allocated_capital``) and ``total_return_pct`` the same as a
    fraction of allocated capital; ``sharpe_ratio`` the annualised Sharpe of the
    daily NAV series, or ``None`` until enough history exists.
    """

    current_value: float
    realised_pnl: float
    unrealised_pnl: float
    total_return: float
    total_return_pct: float
    sharpe_ratio: float | None


def session_kpis(
    session: Session,
    *,
    session_id: uuid.UUID,
    broker: Broker,
) -> SessionKpis:
    """Compute a session's live performance KPIs (404 via ``SessionNotFoundError``).

    Marks the session's open positions to market via ``broker`` for the live
    figures, reads the cumulative realised P&L from the session row, derives the
    absolute and fractional total return against allocated capital, and computes
    the Sharpe ratio from the session's ordered daily-return snapshots. The
    risk-free rate is the configured annual rate converted to a per-day rate.
    """
    session_row = get_session(session, session_id)
    valuation = compute_session_value(session, session_id=session_id, broker=broker)

    allocated = session_row.allocated_capital
    total_return = valuation.total_value - allocated
    total_return_pct = total_return / allocated if allocated > 0 else 0.0

    snapshots = list_value_snapshots(session, session_id=session_id)
    daily_returns = [snap.daily_pnl_pct for snap in snapshots]
    daily_risk_free = settings.SHARPE_RISK_FREE_RATE / SHARPE_TRADING_DAYS_PER_YEAR

    return SessionKpis(
        current_value=valuation.total_value,
        realised_pnl=session_row.total_pnl,
        unrealised_pnl=valuation.unrealized_pnl,
        total_return=total_return,
        total_return_pct=total_return_pct,
        sharpe_ratio=sharpe_ratio(daily_returns, risk_free=daily_risk_free),
    )
