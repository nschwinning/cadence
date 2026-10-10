"""Automatic stop-loss scan for opted-in AI sessions.

Marks each held position against a live quote and fully exits one that has breached
``avg_cost x (1 - stop_loss_pct)`` (equity exits gated on market hours, crypto 24/7),
recording the sale, realized P&L, the flat fee, a ``stop_loss`` run and a cooldown
quarantine, then firing a best-effort notification. Per-session/per-position work is
isolated so one failure never aborts the scan.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from cadence.ai_portfolio._helpers import (
    _asset_class_map,
    _elapsed_ms,
    _order_action,
)
from cadence.ai_portfolio.constants import AI_STRATEGY_KEY
from cadence.ai_portfolio.executor import AIPortfolioExecutor
from cadence.ai_portfolio.notifications import _notify_safely, _stop_loss_message
from cadence.assets import service as assets_service
from cadence.broker.base import Broker
from cadence.broker.models import AssetClass, Position
from cadence.config import settings
from cadence.notify.base import Notifier
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import (
    STOP_LOSS_RUN_TRIGGER,
    STOP_LOSS_SIGNAL_TYPE,
    RunStatus,
    SessionStatus,
)
from cadence.paper_trading.models import PaperTradingSession, SessionPosition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StopLossOutcome:
    """One stopped-out position recorded by a scan (for the endpoint summary)."""

    session_id: uuid.UUID
    ticker: str
    quantity: float
    exit_price: float
    realized_pnl: float


def _trading_days_ahead(start: datetime, trading_days: int) -> datetime:
    """Return ``start`` advanced by ``trading_days`` weekday (Mon–Fri) days.

    A weekday approximation of market days (no exchange-holiday calendar): exact
    calendar precision is not required for a cooldown. ``trading_days <= 0`` returns
    ``start`` unchanged.
    """
    moment = start
    remaining = trading_days
    while remaining > 0:
        moment += timedelta(days=1)
        if moment.weekday() < 5:  # Mon–Fri
            remaining -= 1
    return moment


def scan_stop_losses(
    session: Session,
    *,
    broker: Broker,
    notifier: Notifier | None = None,
) -> list[StopLossOutcome]:
    """Scan all active opted-in sessions and stop out breached positions.

    For every active AI session that opted into the automatic stop-loss, each held
    position is marked against a live quote (batched across the deduped union of held
    tickers) and fully exited when ``price ≤ avg_cost × (1 − stop_loss_pct)``. Equity
    exits are guarded by market status (only when the equities market is open); crypto
    exits run around the clock. A position whose quote is missing is left untouched for
    the next scan. Each stop-out reuses the shared recording path — a ``stop_loss``
    trade with no AI-event reference, a closed position with realized P&L, the flat
    transaction cost, a ``stop_loss`` session run, a cooldown quarantine, and a
    best-effort notification. Per-session and per-position work is wrapped so one
    failure never aborts the rest of the scan. Returns the stop-outs recorded.
    """
    sessions = paper_service.list_sessions(
        session, status=SessionStatus.ACTIVE, limit=500
    )
    targets = [
        s
        for s in sessions
        if s.strategy_key == AI_STRATEGY_KEY
        and s.stop_loss_enabled
        and s.stop_loss_pct
    ]
    if not targets:
        return []

    universe = assets_service.list_assets(session)
    asset_classes = _asset_class_map(universe)
    market_open = broker.is_market_open()

    # Read every opted-in session's ledger once, then price the deduped union of held
    # tickers in a single batched quote request (respecting the rate limit).
    ledgers = {s.id: paper_service.list_open_positions(session, s.id) for s in targets}
    all_tickers = sorted(
        {
            entry.ticker
            for entries in ledgers.values()
            for entry in entries
            if entry.quantity
        }
    )
    quotes: dict[str, Any] = {}
    if all_tickers:
        try:
            quotes = broker.get_quotes(all_tickers)
        except Exception as exc:  # noqa: BLE001 - pricing is best-effort
            logger.warning("stop-loss: batched quote fetch failed: %s", exc)
            quotes = {}

    outcomes: list[StopLossOutcome] = []
    for session_row in targets:
        try:
            outcomes.extend(
                _scan_session_stop_losses(
                    session,
                    session_row,
                    ledger=ledgers[session_row.id],
                    quotes=quotes,
                    asset_classes=asset_classes,
                    market_open=market_open,
                    broker=broker,
                    notifier=notifier,
                )
            )
        except Exception as exc:  # noqa: BLE001 - one session must not abort the scan
            session.rollback()
            logger.error(
                "stop-loss scan failed for session %s: %s", session_row.id, exc
            )

    if outcomes:
        logger.info("Stop-loss scan stopped out %s position(s)", len(outcomes))
    return outcomes


def _scan_session_stop_losses(
    session: Session,
    session_row: PaperTradingSession,
    *,
    ledger: list[SessionPosition],
    quotes: dict[str, Any],
    asset_classes: dict[str, AssetClass],
    market_open: bool,
    broker: Broker,
    notifier: Notifier | None,
) -> list[StopLossOutcome]:
    """Evaluate and stop out one session's breached positions; return the stop-outs."""
    threshold = session_row.stop_loss_pct
    if not threshold:
        return []

    outcomes: list[StopLossOutcome] = []
    for entry in ledger:
        try:
            if not entry.quantity:
                continue
            cls = asset_classes.get(entry.ticker, AssetClass.EQUITY)
            # Equity exits only when the market is open; crypto trades 24/7.
            if cls == AssetClass.EQUITY and not market_open:
                continue
            price = paper_service.quote_price(quotes.get(entry.ticker))
            if price is None:
                # Missing quote: leave the position untouched for the next scan.
                continue
            trigger = entry.avg_cost * (1 - threshold)
            if price > trigger:
                continue
            outcome = _stop_out_position(
                session,
                session_row,
                entry,
                cls,
                broker=broker,
                notifier=notifier,
            )
            if outcome is not None:
                outcomes.append(outcome)
        except Exception as exc:  # noqa: BLE001 - one ticker must not abort the session
            session.rollback()
            logger.error(
                "stop-loss failed for %s (session %s): %s",
                entry.ticker,
                session_row.id,
                exc,
            )
    return outcomes


def _stop_out_position(
    session: Session,
    session_row: PaperTradingSession,
    entry: SessionPosition,
    cls: AssetClass,
    *,
    broker: Broker,
    notifier: Notifier | None,
) -> StopLossOutcome | None:
    """Fully exit one breached position and record it as stop-loss activity.

    Sells the whole position through the executor's close path, then records a
    ``stop_loss`` trade (no AI-event reference), a closed position with realized P&L
    (the asset-class-aware transaction fee is charged at ``record_trade``), a
    ``stop_loss`` session run, and a cooldown quarantine, and fires a best-effort
    notification.
    Returns the outcome, or ``None`` when the sell did not execute.
    """
    t0 = time.monotonic()
    position = Position(
        symbol=entry.ticker,
        quantity=entry.quantity,
        avg_cost=entry.avg_cost,
    )
    executor = AIPortfolioExecutor(broker, session_row.allocated_capital)
    trade_results = executor.execute_close(
        {entry.ticker: position}, asset_classes={entry.ticker: cls}
    )
    result = next((tr for tr in trade_results if tr.executed), None)
    if result is None:
        logger.info(
            "stop-loss: sell for %s (session %s) did not execute",
            entry.ticker,
            session_row.id,
        )
        return None

    fill_price = result.filled_price or result.price or 0.0
    side = _order_action(result.side)

    paper_service.record_trade(
        session,
        session_id=session_row.id,
        ticker=result.ticker,
        side=side,
        quantity=result.shares,
        price=result.price or 0.0,
        signal_type=STOP_LOSS_SIGNAL_TYPE,
        asset_class=cls,
        order_id=result.order_id,
        order_status=result.order_status,
        filled_price=result.filled_price,
        ai_portfolio_event_id=None,
    )

    realized_pnl = 0.0
    now = datetime.now(tz=UTC)
    basis = paper_service.get_position_entry_basis(session, session_row.id, result.ticker)
    if basis is not None:
        entry_price, entry_date = basis
        closed = paper_service.record_closed_position(
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
        realized_pnl = closed.realized_pnl

    paper_service.apply_fill_to_ledger(
        session,
        session_id=session_row.id,
        ticker=result.ticker,
        side=side,
        shares=result.shares,
        price=fill_price,
    )

    paper_service.record_session_run(
        session,
        session_id=session_row.id,
        signals_scanned=1,
        signals_actionable=1,
        orders_executed=1,
        orders_skipped=0,
        details=[result.to_dict()],
        status=RunStatus.SUCCESS,
        run_trigger=STOP_LOSS_RUN_TRIGGER,
        duration_ms=_elapsed_ms(t0),
    )
    paper_service.update_session_last_run(
        session, session_row.id, trades_delta=1, pnl_delta=realized_pnl
    )

    # Quarantine the ticker so the next rebalance cannot immediately re-buy it.
    paper_service.add_stop_loss_quarantine(
        session,
        session_id=session_row.id,
        ticker=result.ticker,
        excluded_until=_trading_days_ahead(
            now, settings.STOP_LOSS_COOLDOWN_TRADING_DAYS
        ),
    )

    logger.info(
        "stop-loss: exited %s %s @ ~$%.2f (session %s)",
        result.shares,
        result.ticker,
        fill_price,
        session_row.id,
    )

    if notifier is not None:
        try:
            label = session_row.portfolio_name or session_row.strategy_key
        except Exception:  # noqa: BLE001 - fall back to the strategy key for the label
            label = session_row.strategy_key
        _notify_safely(
            notifier,
            title=f"Cadence: {label} stop-loss",
            message=_stop_loss_message(
                label, result.ticker, result.shares, fill_price, realized_pnl
            ),
        )

    return StopLossOutcome(
        session_id=session_row.id,
        ticker=result.ticker,
        quantity=result.shares,
        exit_price=fill_price,
        realized_pnl=realized_pnl,
    )
