"""AI-portfolio service: orchestration for build and rebalance jobs.

Routers/background jobs stay thin and delegate here. A job's whole lifecycle is
recorded on an ``ai_portfolio_events`` row while persistence of the portfolio,
the paper-trading session, its trades, runs, and closed positions is reused from
the portfolios and paper-trading domains (never re-implemented here).

- **Build**: run the agent → create an AI-managed :class:`Portfolio` and a
  :class:`PaperTradingSession` → size and place opening orders via the
  :class:`AIPortfolioExecutor` against the :class:`Broker` → record trades + a
  session run → mark the event ``succeeded``/``partial``/``failed``.
- **Rebalance**: guard on ``broker.is_market_open()`` (record a ``skipped`` run
  and event when closed) → read positions/account → run the agent → close then
  open via the executor → record trades + closed positions + a session run →
  mark the event terminal.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.ai_portfolio.agent import AIPortfolioAgent
from cadence.ai_portfolio.constants import (
    AI_STRATEGY_KEY,
    EventStatus,
    EventType,
)
from cadence.ai_portfolio.errors import (
    AIPortfolioValidationError,
    EventNotFoundError,
)
from cadence.ai_portfolio.executor import AIPortfolioExecutor, TradeResult
from cadence.ai_portfolio.models import AIPortfolioEvent
from cadence.assets import service as assets_service
from cadence.assets.market_data import MarketDataProvider
from cadence.assets.models import Asset
from cadence.broker.base import Broker
from cadence.broker.models import OrderSide, Position
from cadence.config import settings
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import RunStatus, ScheduleMode
from cadence.portfolios import service as portfolios_service
from cadence.portfolios.constants import PortfolioSource, RiskProfile

logger = logging.getLogger(__name__)

_VALID_RISK_PROFILES = {profile.value for profile in RiskProfile}


@dataclass(frozen=True)
class AIBuildParams:
    """Inputs for a build job, persisted on the event's ``request_payload``.

    The build allocates over the entire current asset universe (with bounded
    discovery), so no ticker list or per-asset/position caps are accepted.
    """

    allocated_capital: float = 100000.0
    risk_profile: str = "balanced"
    daily_rebalancing: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "allocated_capital": self.allocated_capital,
            "risk_profile": self.risk_profile,
            "daily_rebalancing": self.daily_rebalancing,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> AIBuildParams:
        return cls(
            allocated_capital=float(payload.get("allocated_capital", 100000.0)),
            risk_profile=str(payload.get("risk_profile", "balanced")),
            daily_rebalancing=bool(payload.get("daily_rebalancing", False)),
        )


# --------------------------------------------------------------------------- #
# Event CRUD
# --------------------------------------------------------------------------- #


def get_event(session: Session, event_id: uuid.UUID) -> AIPortfolioEvent:
    """Return an event by id or raise :class:`EventNotFoundError`."""
    event = session.get(AIPortfolioEvent, event_id)
    if event is None:
        raise EventNotFoundError(f"AI portfolio event {event_id} not found")
    return event


def list_session_events(
    session: Session, session_id: uuid.UUID, *, limit: int = 20
) -> list[AIPortfolioEvent]:
    """Return a session's AI events (build + rebalances), newest first."""
    stmt = (
        select(AIPortfolioEvent)
        .where(AIPortfolioEvent.session_id == session_id)
        .order_by(AIPortfolioEvent.created_at.desc(), AIPortfolioEvent.id.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())


def create_build_event(session: Session, params: AIBuildParams) -> AIPortfolioEvent:
    """Validate the request and insert a queued build event; return it.

    The build allocates over the entire asset universe, so the only validation is
    that the universe is non-empty.

    Raises:
        AIPortfolioValidationError: if the asset universe is empty.
    """
    if not assets_service.list_assets(session, limit=1):
        raise AIPortfolioValidationError(
            "asset universe is empty; add assets before building"
        )

    event = AIPortfolioEvent(
        event_type=EventType.BUILD.value,
        status=EventStatus.QUEUED.value,
        request_payload=params.to_payload(),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def create_rebalance_event(
    session: Session, session_id: uuid.UUID
) -> AIPortfolioEvent:
    """Insert a queued rebalance event for a session; return it."""
    event = AIPortfolioEvent(
        session_id=session_id,
        event_type=EventType.REBALANCE.value,
        status=EventStatus.QUEUED.value,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def get_inflight_rebalance_event(
    session: Session, session_id: uuid.UUID
) -> AIPortfolioEvent | None:
    """Return a non-terminal rebalance event for the session, if any (newest first)."""
    stmt = (
        select(AIPortfolioEvent)
        .where(
            AIPortfolioEvent.session_id == session_id,
            AIPortfolioEvent.event_type == EventType.REBALANCE.value,
            AIPortfolioEvent.status.in_(
                [EventStatus.QUEUED.value, EventStatus.RUNNING.value]
            ),
        )
        .order_by(AIPortfolioEvent.created_at.desc(), AIPortfolioEvent.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


# --------------------------------------------------------------------------- #
# Build flow
# --------------------------------------------------------------------------- #


def run_build_event(
    session: Session,
    event_id: uuid.UUID,
    agent: AIPortfolioAgent,
    broker: Broker,
    provider: MarketDataProvider,
) -> None:
    """Drive a queued build event to a terminal status.

    The agent allocates over the full current asset universe and may discover a
    bounded number of new assets; discovered tickers are added to the universe
    best-effort via ``provider``.
    """
    t0 = time.monotonic()
    event = get_event(session, event_id)
    event.status = EventStatus.RUNNING.value
    session.commit()

    try:
        params = AIBuildParams.from_payload(event.request_payload or {})
        universe = assets_service.list_assets(session)
        candidates = _candidates_from_universe(universe)

        result = agent.build(candidates=candidates, risk_profile=params.risk_profile)
        agent_output = result.model_dump(mode="json")

        stock_tickers = _normalize_tickers([s.ticker for s in result.stocks])
        universe_tickers = {a.ticker for a in universe}
        discovered = [t for t in stock_tickers if t not in universe_tickers]
        _add_discovered_assets(session, discovered, provider)

        portfolio = portfolios_service.create_portfolio(
            session,
            name=result.portfolio_name,
            stocks=stock_tickers,
            source=PortfolioSource.AI_MANAGED,
            description=result.overall_thesis[:500],
            risk_profile=_risk_profile(params.risk_profile),
            max_allocation_pct=1.0,
            source_run_id=str(event.id),
        )

        schedule_mode = (
            ScheduleMode.DAILY_REBALANCING
            if params.daily_rebalancing
            else ScheduleMode.MANUAL
        )
        session_row = paper_service.create_session(
            session,
            portfolio_id=portfolio.id,
            strategy_key=AI_STRATEGY_KEY,
            allocated_capital=params.allocated_capital,
            max_allocation_pct=portfolio.max_allocation_pct,
            schedule_mode=schedule_mode,
        )
        session_row.session_metadata = {
            "session_type": "ai_managed",
            "risk_profile": params.risk_profile,
            "build_event_id": str(event.id),
            "portfolio_id": str(portfolio.id),
        }
        event.session_id = session_row.id
        event.portfolio_id = portfolio.id
        session.commit()

        executor = AIPortfolioExecutor(broker, params.allocated_capital)
        trade_results = executor.execute_build(result.stocks)

        executed = _record_trades(
            session, session_row.id, trade_results, signal_prefix="ai_build"
        )
        paper_service.record_session_run(
            session,
            session_id=session_row.id,
            signals_scanned=len(result.stocks),
            signals_actionable=len(result.stocks),
            orders_executed=executed,
            orders_skipped=len(result.stocks) - executed,
            details=[tr.to_dict() for tr in trade_results],
            status=RunStatus.SUCCESS,
            run_trigger="ai_build",
            duration_ms=_elapsed_ms(t0),
        )
        paper_service.update_session_last_run(
            session, session_row.id, trades_delta=executed
        )

        all_executed = bool(trade_results) and all(tr.executed for tr in trade_results)
        status = EventStatus.SUCCEEDED if all_executed else EventStatus.PARTIAL
        _finish_event(
            session,
            event,
            status,
            result_payload=agent_output,
            actions_taken=[tr.to_dict() for tr in trade_results],
            duration_ms=_elapsed_ms(t0),
        )
        logger.info(
            "AI portfolio build %s completed: %s/%s trades executed",
            event.id,
            executed,
            len(result.stocks),
        )
    except Exception as exc:  # noqa: BLE001 - persisted as the event's failure reason
        session.rollback()
        logger.error("AI portfolio build %s failed: %s", event_id, exc)
        _fail_event(session, event_id, str(exc) or exc.__class__.__name__, _elapsed_ms(t0))


# --------------------------------------------------------------------------- #
# Rebalance flow
# --------------------------------------------------------------------------- #


def run_rebalance_event(
    session: Session,
    event_id: uuid.UUID,
    agent: AIPortfolioAgent,
    broker: Broker,
    provider: MarketDataProvider,
) -> None:
    """Drive a queued rebalance event to a terminal status.

    When the market is closed the job is a no-op: a ``skipped`` run is recorded
    (no orders) and the event is marked ``skipped``. Otherwise the agent returns
    desired end-state target weights across the full universe (with bounded
    discovery), and the executor trades the deltas toward those weights.
    """
    t0 = time.monotonic()
    event = get_event(session, event_id)
    event.status = EventStatus.RUNNING.value
    session.commit()

    try:
        if event.session_id is None:
            raise ValueError("rebalance event has no session")
        session_id = event.session_id
        session_row = paper_service.get_session(session, session_id)
        portfolio = portfolios_service.get_portfolio(session, session_row.portfolio_id)

        # Market-open guard: closed => record a skipped run and event, no orders.
        if not broker.is_market_open():
            paper_service.record_session_run(
                session,
                session_id=session_id,
                signals_scanned=0,
                signals_actionable=0,
                orders_executed=0,
                orders_skipped=0,
                details=[{"skipped": True, "reason": "market closed"}],
                status=RunStatus.SUCCESS,
                run_trigger="ai_rebalance",
                duration_ms=_elapsed_ms(t0),
            )
            _finish_event(
                session,
                event,
                EventStatus.SKIPPED,
                result_payload=None,
                actions_taken=[],
                duration_ms=_elapsed_ms(t0),
            )
            logger.info("AI rebalance %s skipped: market closed", event.id)
            return

        positions = {pos.symbol: pos for pos in broker.get_positions()}
        account = broker.get_account_info()

        universe = assets_service.list_assets(session)
        candidates = _candidates_from_universe(universe)
        holdings = _build_holdings(portfolio.stocks, positions)
        account_summary = {
            "portfolio_value": account.portfolio_value,
            "cash_available": account.buying_power,
            "total_unrealized_pnl": account.unrealized_pnl,
        }

        result = agent.rebalance(
            holdings=holdings,
            account_summary=account_summary,
            candidates=candidates,
        )
        agent_output = result.model_dump(mode="json")

        # Best-effort add of any discovered target ticker not yet in the universe.
        universe_tickers = {a.ticker for a in universe}
        target_tickers = _normalize_tickers(
            [t.ticker for t in result.target_allocations]
        )
        discovered = [t for t in target_tickers if t not in universe_tickers]
        _add_discovered_assets(session, discovered, provider)

        executor = AIPortfolioExecutor(broker, session_row.allocated_capital)
        trade_results = executor.execute_rebalance(
            targets=result.target_allocations,
            current_positions=positions,
        )

        executed, realized_pnl = _apply_rebalance_trades(
            session, session_id, trade_results, positions
        )

        paper_service.record_session_run(
            session,
            session_id=session_id,
            signals_scanned=len(candidates),
            signals_actionable=executed,
            orders_executed=executed,
            orders_skipped=0,
            details=[tr.to_dict() for tr in trade_results],
            status=RunStatus.SUCCESS,
            run_trigger="ai_rebalance",
            duration_ms=_elapsed_ms(t0),
        )
        paper_service.update_session_last_run(
            session, session_id, trades_delta=executed, pnl_delta=realized_pnl
        )

        # End-state holdings are the targets with a non-trivial weight.
        end_state = sorted(
            {
                _normalize_tickers([t.ticker])[0]
                for t in result.target_allocations
                if t.allocation_pct > 0 and t.ticker.strip()
            }
        )
        if end_state and set(end_state) != set(portfolio.stocks):
            portfolios_service.update_portfolio_stocks(session, portfolio.id, end_state)

        all_executed = all(tr.executed for tr in trade_results)
        status = EventStatus.SUCCEEDED if all_executed else EventStatus.PARTIAL
        _finish_event(
            session,
            event,
            status,
            result_payload=agent_output,
            actions_taken=[tr.to_dict() for tr in trade_results],
            duration_ms=_elapsed_ms(t0),
        )
        logger.info("AI rebalance %s completed: %s trades executed", event.id, executed)
    except Exception as exc:  # noqa: BLE001 - persisted as the event's failure reason
        session.rollback()
        logger.error("AI rebalance %s failed: %s", event_id, exc)
        _fail_event(session, event_id, str(exc) or exc.__class__.__name__, _elapsed_ms(t0))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

#: Executor trade side -> broker order action stored on the paper trade. The
#: flows are long-only: "long" is a buy (open/increase), "sell" a reduce/close.
_ORDER_ACTION = {
    "long": OrderSide.BUY,
    "sell": OrderSide.SELL,
}


def _order_action(side: str) -> OrderSide:
    return _ORDER_ACTION.get(side, OrderSide.BUY)


def _candidates_from_universe(assets: list[Asset]) -> list[dict[str, Any]]:
    """Build the enriched candidate records the agent reasons over from the universe."""
    return [
        {
            "ticker": asset.ticker,
            "company_name": asset.name or asset.ticker,
            "sector": asset.sector or "unknown",
            "category": asset.category,
            "is_eligible": asset.is_eligible,
        }
        for asset in assets
    ]


def _add_discovered_assets(
    session: Session,
    discovered: list[str],
    provider: MarketDataProvider,
) -> list[str]:
    """Best-effort add of newly-proposed tickers to the universe (capped).

    Adds at most :data:`settings.AI_PORTFOLIO_MAX_NEW_ASSETS` tickers. Any add that
    fails (unknown ticker, market data unavailable, duplicate) is logged and
    skipped — the ticker is still traded and included in the portfolio.
    """
    added: list[str] = []
    for ticker in discovered[: settings.AI_PORTFOLIO_MAX_NEW_ASSETS]:
        try:
            assets_service.add_asset(session, ticker, provider)
            added.append(ticker)
        except Exception as exc:  # noqa: BLE001 - discovery-add is best-effort
            session.rollback()
            logger.warning("AI discovery: could not add %s: %s", ticker, exc)
    return added


def _normalize_tickers(tickers: list[str]) -> list[str]:
    """Upper-case, strip, drop blanks, and de-duplicate ``tickers`` in order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        symbol = raw.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    return normalized


def _risk_profile(value: str) -> RiskProfile | None:
    return RiskProfile(value) if value in _VALID_RISK_PROFILES else None


def _build_holdings(
    portfolio_stocks: list[str], positions: dict[str, Position]
) -> list[dict[str, Any]]:
    holdings: list[dict[str, Any]] = []
    for ticker in portfolio_stocks:
        pos = positions.get(ticker)
        if pos and pos.quantity != 0:
            entry = pos.avg_cost or 0.0
            current = pos.current_price or 0.0
            holdings.append(
                {
                    "ticker": ticker,
                    "side": "long" if pos.quantity > 0 else "short",
                    "quantity": abs(pos.quantity),
                    "avg_cost": entry,
                    "current_price": current,
                    "unrealized_pnl": pos.unrealized_pnl or 0.0,
                    "pnl_pct": (current / entry - 1) if entry > 0 else 0.0,
                }
            )
    return holdings


def _record_trades(
    session: Session,
    session_id: uuid.UUID,
    trade_results: list[TradeResult],
    *,
    signal_prefix: str,
) -> int:
    """Persist each executed trade; return how many were executed."""
    executed = 0
    for tr in trade_results:
        if not tr.executed:
            continue
        paper_service.record_trade(
            session,
            session_id=session_id,
            ticker=tr.ticker,
            side=_order_action(tr.side),
            quantity=tr.shares,
            price=tr.price or 0.0,
            signal_type=f"{signal_prefix}_{tr.side}",
            order_id=tr.order_id,
            order_status=tr.order_status,
            filled_price=tr.filled_price,
        )
        executed += 1
    return executed


def _apply_rebalance_trades(
    session: Session,
    session_id: uuid.UUID,
    trade_results: list[TradeResult],
    positions: dict[str, Position],
) -> tuple[int, float]:
    """Record rebalance trades + closed positions; return (executed, realized_pnl).

    Sells (side ``"sell"``) that reduce or close a long position record a closed
    position for the sold quantity with its realized P&L. The end-state ticker list
    is derived from the AI targets by the caller, so no add/remove bookkeeping is
    done here.
    """
    executed = 0
    realized_pnl_total = 0.0

    # First-entry date per ticker from this session's own opening trades, so a
    # closed position gets a sensible holding period. Opening/increasing trades
    # carry a signal_type ending in "_long".
    prior_trades = paper_service.get_session_trades(session, session_id, limit=1_000_000)
    first_entry_date: dict[str, datetime] = {}
    for t in sorted(prior_trades, key=lambda tr: tr.executed_at):
        if t.signal_type.endswith("_long") and t.ticker not in first_entry_date:
            first_entry_date[t.ticker] = t.executed_at

    now = datetime.now(tz=UTC)

    for tr in trade_results:
        if not tr.executed:
            continue
        paper_service.record_trade(
            session,
            session_id=session_id,
            ticker=tr.ticker,
            side=_order_action(tr.side),
            quantity=tr.shares,
            price=tr.price or 0.0,
            signal_type=f"ai_rebalance_{tr.side}",
            order_id=tr.order_id,
            order_status=tr.order_status,
            filled_price=tr.filled_price,
        )
        executed += 1

        # A sell reduces/closes an existing long; record realized P&L. `positions`
        # was captured before execution, so avg_cost is the entry price.
        if tr.side == "sell":
            pos = positions.get(tr.ticker)
            if pos is not None:
                entry_price = pos.avg_cost or 0.0
                exit_price = tr.filled_price or tr.price or entry_price
                closed = paper_service.record_closed_position(
                    session,
                    session_id=session_id,
                    ticker=tr.ticker,
                    quantity=tr.shares,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    entry_date=first_entry_date.get(tr.ticker, now),
                    exit_date=now,
                )
                realized_pnl_total += closed.realized_pnl

    return executed, realized_pnl_total


def _finish_event(
    session: Session,
    event: AIPortfolioEvent,
    status: EventStatus,
    *,
    result_payload: dict[str, Any] | None,
    actions_taken: list[dict[str, Any]],
    duration_ms: int,
) -> None:
    event.status = status.value
    event.result_payload = result_payload
    event.actions_taken = actions_taken
    event.duration_ms = duration_ms
    session.commit()


def _fail_event(
    session: Session, event_id: uuid.UUID, error: str, duration_ms: int
) -> None:
    """Best-effort transition of an event to ``failed`` with a reason."""
    event = session.get(AIPortfolioEvent, event_id)
    if event is None:
        return
    event.status = EventStatus.FAILED.value
    event.error = error
    event.duration_ms = duration_ms
    session.commit()


def _elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
