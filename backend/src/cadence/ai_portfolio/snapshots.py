"""End-of-day value snapshots and the daily-run learning snapshot.

Two fan-out jobs over active AI sessions: :func:`snapshot_all_sessions` records the
per-session value snapshot and pushes the daily P&L report; the backend-only
:func:`assemble_daily_run_snapshots` consolidates each session's day (run reasoning
+ reconciled orders + valuation) into a learning row for offline use.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.ai_portfolio.constants import AI_STRATEGY_KEY
from cadence.ai_portfolio.events import session_allows_crypto
from cadence.ai_portfolio.models import AIPortfolioEvent
from cadence.ai_portfolio.notifications import (
    _benchmark_suffix,
    _notify_safely,
    _session_snapshot_message,
)
from cadence.broker.base import Broker
from cadence.notify.base import Notifier
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import SessionStatus
from cadence.paper_trading.models import (
    PaperTrade,
    PaperTradingSession,
    SessionValueSnapshot,
)
from cadence.portfolios import service as portfolios_service

logger = logging.getLogger(__name__)


#: Timezone the end-of-day snapshot date is anchored to (US market close), matching
#: the cron sidecar's schedule timezone.
_SNAPSHOT_TZ = ZoneInfo("America/New_York")


def snapshot_all_sessions(
    session: Session,
    *,
    broker: Broker,
    notifier: Notifier,
    as_of: date | None = None,
) -> list[uuid.UUID]:
    """Record an end-of-day value snapshot for every active AI session and report.

    Fans out over active sessions, keeps only AI-managed ones
    (``strategy_key == AI_STRATEGY_KEY``), and upserts one snapshot per session for
    ``as_of`` (today in the market-close timezone when omitted). Sends **one push
    per session** (titled by its portfolio name) carrying that session's value and
    day P&L, headline KPIs (total return, realized/unrealized P&L, fees, Sharpe),
    its benchmark comparison, and its own best/worst holding. Delivery is
    best-effort — a notifier failure never fails the job (see
    :func:`_notify_safely`). Returns the ids of the sessions snapshotted.

    On a **weekend** (Saturday/Sunday by calendar in :data:`_SNAPSHOT_TZ`, ignoring
    exchange holidays) a session whose **configured** scope does not include crypto
    (stocks-only) is skipped entirely — no snapshot recorded and no push sent —
    since its holdings do not move while the equity market is closed. Crypto/both
    sessions still snapshot and report on weekends, and weekdays are unchanged (all
    active AI sessions).
    """
    if as_of is None:
        as_of = datetime.now(tz=_SNAPSHOT_TZ).date()
    is_weekend = as_of.weekday() >= 5  # Sat=5, Sun=6

    sessions = paper_service.list_sessions(
        session, status=SessionStatus.ACTIVE, limit=500
    )
    targets = [s for s in sessions if s.strategy_key == AI_STRATEGY_KEY]

    snapshotted: list[uuid.UUID] = []
    for session_row in targets:
        # On weekends, a stocks-only session's holdings do not move while the
        # equity market is closed: skip it entirely (no snapshot, no push). Its
        # scope is read from the frozen build metadata, not its current holdings.
        if is_weekend and not session_allows_crypto(session_row):
            continue
        snapshot = paper_service.record_value_snapshot(
            session, session_id=session_row.id, as_of=as_of, broker=broker
        )
        snapshotted.append(session_row.id)

        try:
            portfolio = portfolios_service.get_portfolio(
                session, session_row.portfolio_id
            )
            label = portfolio.name
        except Exception:  # noqa: BLE001 - fall back to the strategy key for the label
            label = session_row.strategy_key
        benchmark_suffix = _benchmark_suffix(
            session, session_row, snapshot, as_of=as_of
        )
        kpis = paper_service.session_kpis(
            session, session_id=session_row.id, broker=broker
        )
        holdings = [
            (str(pos.get("ticker", "?")), float(pos.get("return_pct", 0.0)))
            for pos in snapshot.positions
        ]
        _notify_safely(
            notifier,
            title=f"Cadence: {label} daily P&L",
            message=_session_snapshot_message(
                snapshot, kpis, benchmark_suffix, holdings
            ),
        )

    if snapshotted:
        logger.info("Daily snapshot recorded for %s AI session(s)", len(snapshotted))
    return snapshotted


def _find_day_rebalance_event(
    session: Session, session_id: uuid.UUID, run_date: date
) -> AIPortfolioEvent | None:
    """Return the session's most recent run whose calendar day is ``run_date``.

    "Calendar day" is measured in :data:`_SNAPSHOT_TZ` — the same timezone the daily
    snapshot job uses to derive the day — so the learning row and the value snapshot
    agree on the day boundary. Returns ``None`` when the session had no run that day
    (a weekend, a skipped run, or a stocks-only idle day).
    """
    start = datetime(
        run_date.year, run_date.month, run_date.day, tzinfo=_SNAPSHOT_TZ
    )
    end = start + timedelta(days=1)
    stmt = (
        select(AIPortfolioEvent)
        .where(
            AIPortfolioEvent.session_id == session_id,
            AIPortfolioEvent.created_at >= start,
            AIPortfolioEvent.created_at < end,
        )
        .order_by(AIPortfolioEvent.created_at.desc(), AIPortfolioEvent.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


def _order_document(trade: PaperTrade) -> dict[str, Any]:
    """The reconciled view of a single filled order for the learning document.

    Reads the authoritative ``filled_price``/``filled_at``/``order_status`` written
    by reconciliation onto the ``PaperTrade`` row (the reason assembly runs after the
    P&L/reconciliation job) rather than the as-decided price in ``run_stats``.
    """
    return {
        "ticker": trade.ticker,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": trade.price,
        "notional": trade.notional,
        "signal_type": trade.signal_type,
        "order_id": trade.order_id,
        "order_status": trade.order_status,
        "filled_price": trade.filled_price,
        "filled_at": trade.filled_at.isoformat() if trade.filled_at else None,
        "executed_at": trade.executed_at.isoformat() if trade.executed_at else None,
        "fee": trade.fee,
    }


def _build_run_document(
    event: AIPortfolioEvent | None,
    trades: list[PaperTrade],
    snapshot: SessionValueSnapshot,
) -> dict[str, Any]:
    """Assemble the consolidated learning ``document`` from already-persisted data.

    ``run`` carries the day's rebalance reasoning/result (``result_payload``), the
    indicator values the agent saw (``trend_context``), and the run outcome stats
    (``run_stats``) — or ``None`` on a day with no run. ``orders`` is the day's
    reconciled filled orders and ``orders_count`` their number (``0`` on a no-run
    day); ``fees_total`` is the sum of those orders' recorded transaction fees
    (``0`` on a no-run day or for orders predating per-order fee recording).
    ``valuation`` is the day's P&L from the value snapshot. No indicator is
    recomputed and the agent is not re-run.
    """
    run: dict[str, Any] | None = None
    if event is not None:
        run = {
            "event_id": str(event.id),
            "event_type": event.event_type,
            "status": event.status,
            "result_payload": event.result_payload,
            "trend_context": event.trend_context,
            "run_stats": event.run_stats,
            "duration_ms": event.duration_ms,
            "error": event.error,
        }
    return {
        "run": run,
        "orders": [_order_document(t) for t in trades],
        "orders_count": len(trades),
        "fees_total": sum(t.fee for t in trades),
        "valuation": {
            "total_value": snapshot.total_value,
            "cash_value": snapshot.cash_value,
            "positions_value": snapshot.positions_value,
            "daily_pnl": snapshot.daily_pnl,
            "daily_pnl_pct": snapshot.daily_pnl_pct,
            "positions": snapshot.positions,
        },
    }


def _assemble_session_daily_run(
    session: Session, session_row: PaperTradingSession, run_date: date
) -> bool:
    """Upsert one consolidated learning snapshot for ``session_row`` on ``run_date``.

    Returns ``True`` when a row was recorded. A session with no value snapshot for the
    day is skipped (returns ``False``) — keeping the learning table aligned 1:1 with
    the P&L table. On a day with a value snapshot but no run, the row is recorded with
    the run/orders portions absent.
    """
    value_snapshot = paper_service.get_value_snapshot(
        session, session_id=session_row.id, snapshot_date=run_date
    )
    if value_snapshot is None:
        return False

    event = _find_day_rebalance_event(session, session_row.id, run_date)
    trades = (
        paper_service.get_trades_by_event(session, event.id)
        if event is not None
        else []
    )
    document = _build_run_document(event, trades, value_snapshot)
    paper_service.record_daily_run_snapshot(
        session,
        session_id=session_row.id,
        portfolio_id=session_row.portfolio_id,
        run_date=run_date,
        ai_portfolio_event_id=event.id if event is not None else None,
        document=document,
    )
    return True


def assemble_daily_run_snapshots(
    session: Session,
    *,
    as_of: date | None = None,
) -> list[uuid.UUID]:
    """Assemble the backend-only consolidated daily-run learning snapshots for the day.

    A **dedicated** job, separate from both the rebalance run and the end-of-day
    value-snapshot (P&L) job, and intended (a deployment/cron concern) to run **after**
    the P&L job so the day's value snapshot exists and the day's orders are reconciled.
    Selects the day's sessions with the **same selection semantics** as
    :func:`snapshot_all_sessions` (active AI-managed sessions; on a weekend only those
    whose configured scope includes crypto), assembles each that has a value snapshot
    for the day, and upserts one row per ``(session_id, run_date)``.

    Best-effort per session: a failure assembling one session's learning snapshot is
    logged and skipped so it never aborts the batch. Returns the ids of the sessions
    for which a learning snapshot was recorded.
    """
    if as_of is None:
        as_of = datetime.now(tz=_SNAPSHOT_TZ).date()
    is_weekend = as_of.weekday() >= 5  # Sat=5, Sun=6

    sessions = paper_service.list_sessions(
        session, status=SessionStatus.ACTIVE, limit=500
    )
    targets = [s for s in sessions if s.strategy_key == AI_STRATEGY_KEY]

    recorded: list[uuid.UUID] = []
    for session_row in targets:
        # Mirror the P&L job's weekend gating: a stocks-only session is not
        # snapshotted on a weekend, so it has no value snapshot and nothing to learn.
        if is_weekend and not session_allows_crypto(session_row):
            continue
        try:
            if _assemble_session_daily_run(session, session_row, as_of):
                recorded.append(session_row.id)
        except Exception:  # one session's failure must not abort the batch
            session.rollback()
            logger.exception(
                "Failed to assemble daily-run learning snapshot for session %s",
                session_row.id,
            )

    if recorded:
        logger.info(
            "Daily-run learning snapshot recorded for %s AI session(s)", len(recorded)
        )
    return recorded
