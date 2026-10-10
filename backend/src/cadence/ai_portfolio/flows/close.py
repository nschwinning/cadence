"""Close flow: liquidate a session's open positions and stop it, synchronously.

Runs inline (no agent/web search): fully sells every held position regardless of
market hours, records the sells and realized P&L against a ``close`` event, moves
the session to ``stopped``, and returns the terminal event.
"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy.orm import Session

from cadence.ai_portfolio._helpers import (
    _apply_rebalance_trades,
    _asset_class_map,
    _build_run_stats,
    _elapsed_ms,
    _fail_event,
    _finish_event,
)
from cadence.ai_portfolio.constants import AI_STRATEGY_KEY, EventStatus
from cadence.ai_portfolio.errors import SessionNotEligibleError
from cadence.ai_portfolio.events import (
    create_close_event,
    get_inflight_rebalance_event,
)
from cadence.ai_portfolio.executor import AIPortfolioExecutor
from cadence.ai_portfolio.models import AIPortfolioEvent
from cadence.ai_portfolio.notifications import (
    _notify_safely,
    _rebalance_success_message,
)
from cadence.assets import service as assets_service
from cadence.broker.base import Broker
from cadence.broker.models import Position
from cadence.notify.base import Notifier
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import RunStatus, SessionStatus
from cadence.portfolios import service as portfolios_service

logger = logging.getLogger(__name__)


def close_session(
    session: Session,
    session_id: uuid.UUID,
    broker: Broker,
    notifier: Notifier | None = None,
) -> AIPortfolioEvent:
    """Liquidate all of a session's open positions and stop it, synchronously.

    Unlike build/rebalance this runs inline (no agent, no web search, so it's
    fast): every position the session holds is fully sold — regardless of market
    hours — the sells and their realized P&L are recorded against a ``close``
    event, and the session is moved to ``stopped`` so it is excluded from further
    rebalances and the daily fan-out. Returns the terminal event.

    Raises:
        SessionNotFoundError: if the session does not exist.
        SessionNotEligibleError: if the session is not an active AI-managed session,
            or a rebalance is still in flight for it.
    """
    t0 = time.monotonic()
    session_row = paper_service.get_session(session, session_id)
    if session_row.strategy_key != AI_STRATEGY_KEY:
        raise SessionNotEligibleError("only AI-managed sessions can be closed")
    if session_row.status != SessionStatus.ACTIVE.value:
        raise SessionNotEligibleError(f"session is {session_row.status}, not active")
    if get_inflight_rebalance_event(session, session_id) is not None:
        raise SessionNotEligibleError(
            "a rebalance is in progress; wait for it to finish before closing"
        )

    event = create_close_event(session, session_id)
    event.status = EventStatus.RUNNING.value
    session.commit()

    try:
        portfolio = portfolios_service.get_portfolio(session, session_row.portfolio_id)

        # The session's ledger is the source of truth for what it holds; liquidate
        # exactly its open positions (no account-wide intersection).
        ledger = paper_service.list_open_positions(session, session_id)
        positions = {
            entry.ticker: Position(
                symbol=entry.ticker,
                quantity=entry.quantity,
                avg_cost=entry.avg_cost,
            )
            for entry in ledger
            if entry.quantity
        }

        asset_classes = _asset_class_map(assets_service.list_assets(session))
        executor = AIPortfolioExecutor(broker, session_row.allocated_capital)
        trade_results = executor.execute_close(positions, asset_classes=asset_classes)

        executed, realized_pnl = _apply_rebalance_trades(
            session,
            session_id,
            trade_results,
            event_id=event.id,
            asset_classes=asset_classes,
            signal_prefix="ai_close",
        )

        paper_service.record_session_run(
            session,
            session_id=session_id,
            signals_scanned=len(positions),
            signals_actionable=executed,
            orders_executed=executed,
            orders_skipped=len(trade_results) - executed,
            details=[tr.to_dict() for tr in trade_results],
            status=RunStatus.SUCCESS,
            run_trigger="ai_close",
            duration_ms=_elapsed_ms(t0),
            ai_portfolio_event_id=event.id,
        )
        paper_service.update_session_last_run(
            session, session_id, trades_delta=executed, pnl_delta=realized_pnl
        )
        # Stop the session even if some orders failed: the user asked to close it,
        # and any leftover positions are surfaced as skipped rows on the event.
        paper_service.update_session_status(session, session_id, SessionStatus.STOPPED)

        all_executed = all(tr.executed for tr in trade_results)
        status = EventStatus.SUCCEEDED if all_executed else EventStatus.PARTIAL
        _finish_event(
            session,
            event,
            status,
            result_payload=None,
            actions_taken=[tr.to_dict() for tr in trade_results],
            duration_ms=_elapsed_ms(t0),
            run_stats=_build_run_stats(
                trade_results=trade_results,
                executed=executed,
                all_executed=all_executed,
                realized_pnl=realized_pnl,
            ),
        )
        logger.info(
            "AI close %s completed: %s/%s positions liquidated",
            event.id,
            executed,
            len(trade_results),
        )

        if notifier is not None and executed > 0:
            _notify_safely(
                notifier,
                title=f"Cadence: {portfolio.name} closed",
                message=_rebalance_success_message(
                    portfolio.name, trade_results, realized_pnl
                ),
            )

        session.refresh(event)
        return event
    except Exception as exc:  # noqa: BLE001 - persisted as the event's failure reason
        session.rollback()
        logger.error("AI close %s failed: %s", event.id, exc)
        _fail_event(
            session,
            event.id,
            str(exc) or exc.__class__.__name__,
            _elapsed_ms(t0),
        )
        session.refresh(event)
        return event
