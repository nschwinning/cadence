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
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cadence.agents.tools import record_web_searches
from cadence.ai_portfolio.agent import AIPortfolioAgent
from cadence.ai_portfolio.constants import (
    AI_STRATEGY_KEY,
    EventStatus,
    EventType,
)
from cadence.ai_portfolio.errors import (
    AIPortfolioValidationError,
    EventNotFoundError,
    RebalancePromptNotFoundError,
    SessionNotEligibleError,
)
from cadence.ai_portfolio.executor import AIPortfolioExecutor, TradeResult
from cadence.ai_portfolio.models import AIPortfolioEvent, RebalancePrompt
from cadence.assets import service as assets_service
from cadence.assets.category import AssetCategory, AssetScope, scope_categories
from cadence.assets.market_data import MarketDataProvider
from cadence.assets.models import Asset
from cadence.broker.base import Broker
from cadence.broker.models import AssetClass, OrderSide, Position
from cadence.config import settings
from cadence.notify.base import Notifier
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import RunStatus, ScheduleMode, SessionStatus
from cadence.paper_trading.models import SessionPosition
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

    allocated_capital: float = 10000.0
    risk_profile: str = "balanced"
    asset_types: str = AssetScope.BOTH.value
    daily_rebalancing: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "allocated_capital": self.allocated_capital,
            "risk_profile": self.risk_profile,
            "asset_types": self.asset_types,
            "daily_rebalancing": self.daily_rebalancing,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> AIBuildParams:
        return cls(
            allocated_capital=float(payload.get("allocated_capital", 10000.0)),
            risk_profile=str(payload.get("risk_profile", "balanced")),
            asset_types=str(payload.get("asset_types", AssetScope.BOTH.value)),
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


def list_ai_runs(
    session: Session,
    *,
    event_type: EventType | None = None,
    status: EventStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AIPortfolioEvent]:
    """List AI runs across all sessions, newest first, for the Runs history.

    Optionally filtered by ``event_type`` (build/rebalance) and ``status``.
    Paginated via ``limit``/``offset`` (pair with :func:`count_ai_runs`).
    """
    stmt = select(AIPortfolioEvent).order_by(
        AIPortfolioEvent.created_at.desc(), AIPortfolioEvent.id.desc()
    )
    if event_type is not None:
        stmt = stmt.where(AIPortfolioEvent.event_type == event_type.value)
    if status is not None:
        stmt = stmt.where(AIPortfolioEvent.status == status.value)
    return list(session.execute(stmt.limit(limit).offset(offset)).scalars())


def count_ai_runs(
    session: Session,
    *,
    event_type: EventType | None = None,
    status: EventStatus | None = None,
) -> int:
    """Count AI runs across all sessions, with the same optional filters."""
    stmt = select(func.count()).select_from(AIPortfolioEvent)
    if event_type is not None:
        stmt = stmt.where(AIPortfolioEvent.event_type == event_type.value)
    if status is not None:
        stmt = stmt.where(AIPortfolioEvent.status == status.value)
    return session.execute(stmt).scalar_one()


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


def create_close_event(session: Session, session_id: uuid.UUID) -> AIPortfolioEvent:
    """Insert a queued close event for a session; return it."""
    event = AIPortfolioEvent(
        session_id=session_id,
        event_type=EventType.CLOSE.value,
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

    # Bound at ``with`` entry so any research captured before a mid-run failure is
    # still persisted on the (failed) event.
    research: list[dict[str, Any]] = []
    try:
        params = AIBuildParams.from_payload(event.request_payload or {})
        allowed_categories = scope_categories(params.asset_types)
        universe = assets_service.list_assets(
            session, categories=[c.value for c in allowed_categories]
        )
        candidates = _candidates_from_universe(universe)

        with record_web_searches() as research:
            result = agent.build(
                candidates=candidates, risk_profile=params.risk_profile
            )
        agent_output = result.model_dump(mode="json")

        stock_tickers = _normalize_tickers([s.ticker for s in result.stocks])
        universe_tickers = {a.ticker for a in universe}
        discovered = [t for t in stock_tickers if t not in universe_tickers]
        _add_discovered_assets(
            session, discovered, provider, broker, scope=params.asset_types
        )

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
        # Freeze the currently active rebalance-prompt version onto the session so
        # every rebalance for it uses this version, regardless of later prompt edits.
        frozen_prompt_version = get_active_rebalance_prompt(session).version
        session_row = paper_service.create_session(
            session,
            portfolio_id=portfolio.id,
            strategy_key=AI_STRATEGY_KEY,
            rebalance_prompt_version=frozen_prompt_version,
            allocated_capital=params.allocated_capital,
            max_allocation_pct=portfolio.max_allocation_pct,
            schedule_mode=schedule_mode,
        )
        session_row.session_metadata = {
            "session_type": "ai_managed",
            "risk_profile": params.risk_profile,
            "asset_types": params.asset_types,
            "build_event_id": str(event.id),
            "portfolio_id": str(portfolio.id),
        }
        event.session_id = session_row.id
        event.portfolio_id = portfolio.id
        session.commit()

        # Re-read the universe so discovered crypto is classified, then build the
        # per-ticker class map threaded into the executor.
        asset_classes = _asset_class_map(assets_service.list_assets(session))

        executor = AIPortfolioExecutor(broker, params.allocated_capital)
        trade_results = executor.execute_build(
            result.stocks, asset_classes=asset_classes
        )

        executed = _record_trades(
            session,
            session_row.id,
            trade_results,
            signal_prefix="ai_build",
            event_id=event.id,
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
            research=research,
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
        _fail_event(
            session,
            event_id,
            str(exc) or exc.__class__.__name__,
            _elapsed_ms(t0),
            research=research,
        )


# --------------------------------------------------------------------------- #
# Rebalance flow
# --------------------------------------------------------------------------- #


def get_active_rebalance_prompt(session: Session) -> RebalancePrompt:
    """Return the active rebalance prompt: the row with the highest ``version``.

    The prompt is stored append-only and versioned (see :class:`RebalancePrompt`);
    "active" is simply the latest version. Migration seeds version 1, so a row
    normally always exists.

    Raises:
        RebalancePromptNotFoundError: if no prompt version has been persisted.
    """
    stmt = select(RebalancePrompt).order_by(RebalancePrompt.version.desc()).limit(1)
    prompt = session.execute(stmt).scalars().first()
    if prompt is None:
        raise RebalancePromptNotFoundError(
            "no rebalance prompt is configured; seed version 1 before rebalancing"
        )
    return prompt


def get_rebalance_prompt_by_version(session: Session, version: int) -> RebalancePrompt:
    """Return the rebalance prompt pinned at ``version``.

    Used to resolve a session's frozen rebalance-prompt version so every rebalance
    for that session uses the same prompt, regardless of later prompt edits.

    Raises:
        RebalancePromptNotFoundError: if no prompt with that version exists.
    """
    stmt = select(RebalancePrompt).where(RebalancePrompt.version == version)
    prompt = session.execute(stmt).scalars().first()
    if prompt is None:
        raise RebalancePromptNotFoundError(
            f"rebalance prompt version {version} not found"
        )
    return prompt


def run_rebalance_event(
    session: Session,
    event_id: uuid.UUID,
    agent: AIPortfolioAgent,
    broker: Broker,
    provider: MarketDataProvider,
    notifier: Notifier | None = None,
) -> None:
    """Drive a queued rebalance event to a terminal status.

    When the market is closed the job is a no-op: a ``skipped`` run is recorded
    (no orders) and the event is marked ``skipped``. Otherwise the agent returns
    desired end-state target weights across the full universe (with bounded
    discovery), and the executor trades the deltas toward those weights.

    ``notifier`` is optional: the daily cron path supplies one so an executed
    rebalance (or a failure) is pushed to the user; manual rebalances leave it
    ``None`` and stay silent. Sending is best-effort — a notifier that fails or
    raises never affects the rebalance outcome (see :func:`_notify_safely`).
    """
    t0 = time.monotonic()
    event = get_event(session, event_id)
    event.status = EventStatus.RUNNING.value
    session.commit()

    # Bound at ``with`` entry (below) so research captured before a mid-run failure
    # is still persisted on the (failed) event; stays empty on the skip path.
    research: list[dict[str, Any]] = []
    try:
        if event.session_id is None:
            raise ValueError("rebalance event has no session")
        session_id = event.session_id
        session_row = paper_service.get_session(session, session_id)
        portfolio = portfolios_service.get_portfolio(session, session_row.portfolio_id)

        # Read the scope and risk profile persisted at build. Sessions built before
        # these fields existed default to ``both`` / ``balanced`` (unchanged
        # behaviour). ``risk_profile`` was previously written but never re-read here,
        # so every rebalance silently ran as the agent's default.
        metadata = session_row.session_metadata or {}
        asset_scope = str(metadata.get("asset_types", AssetScope.BOTH.value))
        risk_profile = str(metadata.get("risk_profile", "balanced"))
        allowed_categories = scope_categories(asset_scope)

        # Crypto trades 24/7, so the market-open guard can no longer skip the
        # whole run unconditionally. Read this session's holdings from its ledger
        # (the source of truth) and the class map first, to decide whether anything
        # is tradable while the equities market is closed.
        market_open = broker.is_market_open()
        ledger = paper_service.list_open_positions(session, session_id)
        positions = {
            entry.ticker: Position(
                symbol=entry.ticker,
                quantity=entry.quantity,
                avg_cost=entry.avg_cost,
            )
            for entry in ledger
        }

        universe = assets_service.list_assets(session)
        asset_classes = _asset_class_map(universe)
        any_crypto = _involves_crypto(positions, portfolio.stocks, asset_classes)

        # Nothing tradable: equities market closed and no crypto held/targeted.
        # Record a skipped run and event without ever consulting the agent.
        if not market_open and not any_crypto:
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

        account = broker.get_account_info()

        # Candidates are restricted to the session's asset scope; the full universe
        # (above) still backs the class map so held positions stay classified.
        scoped_universe = [
            asset for asset in universe if asset.category in allowed_categories
        ]
        candidates = _candidates_from_universe(scoped_universe)
        holdings = _build_holdings(ledger, broker, asset_classes)
        account_summary = {
            "portfolio_value": account.portfolio_value,
            "cash_available": account.buying_power,
            "total_unrealized_pnl": account.unrealized_pnl,
        }

        # Use the prompt version frozen onto the session at build time, not
        # whatever is active now, so newer prompt versions never change an
        # already-built session's behavior.
        prompt = get_rebalance_prompt_by_version(
            session, session_row.rebalance_prompt_version
        )
        with record_web_searches() as research:
            result = agent.rebalance(
                holdings=holdings,
                account_summary=account_summary,
                candidates=candidates,
                risk_profile=risk_profile,
                instructions=prompt.instructions,
                input_template=prompt.input_template,
            )
        agent_output = result.model_dump(mode="json")

        # Best-effort add of any discovered target ticker not yet in the universe;
        # out-of-scope discoveries are rejected inside ``_add_discovered_assets``.
        universe_tickers = {a.ticker for a in universe}
        target_tickers = _normalize_tickers(
            [t.ticker for t in result.target_allocations]
        )
        discovered = [t for t in target_tickers if t not in universe_tickers]
        _add_discovered_assets(
            session, discovered, provider, broker, scope=asset_scope
        )

        # Rebuild the class map so any discovered crypto target is classified.
        asset_classes = _asset_class_map(assets_service.list_assets(session))

        executor = AIPortfolioExecutor(broker, session_row.allocated_capital)
        trade_results = executor.execute_rebalance(
            targets=result.target_allocations,
            current_positions=positions,
            asset_classes=asset_classes,
            market_open=market_open,
        )

        executed, realized_pnl = _apply_rebalance_trades(
            session, session_id, trade_results, event_id=event.id
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
            research=research,
        )
        logger.info("AI rebalance %s completed: %s trades executed", event.id, executed)

        # Notify only when the daily path supplied a notifier and orders actually
        # went out; a run that executed nothing is not worth a push.
        if notifier is not None and executed > 0:
            _notify_safely(
                notifier,
                title=f"Cadence: {portfolio.name} rebalanced",
                message=_rebalance_success_message(
                    portfolio.name, trade_results, realized_pnl
                ),
            )
    except Exception as exc:  # noqa: BLE001 - persisted as the event's failure reason
        session.rollback()
        logger.error("AI rebalance %s failed: %s", event_id, exc)
        _fail_event(
            session,
            event_id,
            str(exc) or exc.__class__.__name__,
            _elapsed_ms(t0),
            research=research,
        )
        if notifier is not None:
            _notify_safely(
                notifier,
                title="Cadence: daily rebalance failed",
                message=(
                    f"Rebalance {event_id} failed: {str(exc) or exc.__class__.__name__}"
                ),
            )


# --------------------------------------------------------------------------- #
# Close flow
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Daily value snapshots
# --------------------------------------------------------------------------- #

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
    ``as_of`` (today in the market-close timezone when omitted). Then sends a single
    daily report: a per-session value + P&L line plus the single best- and
    worst-performing individual holding (by return) across all snapshotted sessions,
    omitted when no session holds anything. Delivery is best-effort — a notifier
    failure never fails the job (see :func:`_notify_safely`). Returns the ids of the
    sessions snapshotted.
    """
    if as_of is None:
        as_of = datetime.now(tz=_SNAPSHOT_TZ).date()

    sessions = paper_service.list_sessions(
        session, status=SessionStatus.ACTIVE, limit=500
    )
    targets = [s for s in sessions if s.strategy_key == AI_STRATEGY_KEY]

    report_lines: list[str] = []
    holdings: list[tuple[str, float]] = []
    snapshotted: list[uuid.UUID] = []
    for session_row in targets:
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
        report_lines.append(_session_report_line(label, snapshot))
        for pos in snapshot.positions:
            holdings.append((str(pos.get("ticker", "?")), float(pos.get("return_pct", 0.0))))

    if snapshotted:
        _notify_safely(
            notifier,
            title="Cadence: daily P&L",
            message=_daily_snapshot_message(report_lines, holdings),
        )
        logger.info("Daily snapshot recorded for %s AI session(s)", len(snapshotted))
    return snapshotted


def _signed_money(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}${abs(value):,.2f}"


def _signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}{abs(value) * 100:.2f}%"


def _session_report_line(label: str, snapshot: Any) -> str:
    """One per-session report line: value + the day's absolute/percent P&L."""
    return (
        f"{label}: ${snapshot.total_value:,.2f} "
        f"({_signed_money(snapshot.daily_pnl)}, {_signed_pct(snapshot.daily_pnl_pct)})"
    )


def _best_worst_line(holdings: list[tuple[str, float]]) -> str | None:
    """The best/worst individual holding by return, or ``None`` when none held."""
    if not holdings:
        return None
    best = max(holdings, key=lambda h: h[1])
    worst = min(holdings, key=lambda h: h[1])
    return (
        f"Best: {best[0]} {_signed_pct(best[1])}   "
        f"Worst: {worst[0]} {_signed_pct(worst[1])}"
    )


def _daily_snapshot_message(
    report_lines: list[str], holdings: list[tuple[str, float]]
) -> str:
    """Assemble the daily push body: per-session lines then best/worst holding."""
    lines = list(report_lines)
    best_worst = _best_worst_line(holdings)
    if best_worst is not None:
        lines.append(best_worst)
    return "\n".join(lines)


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


def _notify_safely(notifier: Notifier, *, title: str, message: str) -> None:
    """Send a notification, swallowing any failure.

    The :class:`Notifier` contract already forbids raising, but this guards the
    call site defensively so a misbehaving implementation can never turn a
    successful rebalance into a failure.
    """
    try:
        notifier.send(message, title=title)
    except Exception:
        # Notifications are strictly best-effort: a broken notifier must never
        # turn a successful (or already-failed) rebalance into something worse.
        logger.warning("rebalance notification failed", exc_info=True)


def _rebalance_success_message(
    portfolio_name: str,
    trade_results: list[TradeResult],
    realized_pnl: float,
) -> str:
    """Build the push body for an executed rebalance: per-order lines + P&L."""
    lines = [f"{portfolio_name}: rebalanced"]
    for tr in trade_results:
        if not tr.executed:
            continue
        action = _order_action(tr.side).value.upper()
        price = tr.filled_price if tr.filled_price is not None else tr.price
        at = f" @ ${price:,.2f}" if price is not None else ""
        lines.append(f"{action} {tr.shares:g} {tr.ticker}{at}")
    lines.append(f"Realized P&L: ${realized_pnl:,.2f}")
    return "\n".join(lines)


def _asset_class_map(assets: list[Asset]) -> dict[str, AssetClass]:
    """Map each asset's ticker to its :class:`AssetClass` (crypto iff category).

    The asset record is the single source of truth: a ticker is crypto iff its
    ``category == AssetCategory.CRYPTO``. Tickers not present in the universe are
    absent from the map; callers default them to :attr:`AssetClass.EQUITY`.
    """
    return {
        asset.ticker: (
            AssetClass.CRYPTO
            if asset.category == AssetCategory.CRYPTO.value
            else AssetClass.EQUITY
        )
        for asset in assets
    }


def _involves_crypto(
    positions: dict[str, Position],
    target_tickers: list[str],
    asset_classes: dict[str, AssetClass],
) -> bool:
    """Whether any held position or current target ticker is crypto.

    Used to decide, while the equities market is closed, whether there is any
    tradable crypto (24/7) or the run is a true no-op. ``target_tickers`` are the
    portfolio's current end-state holdings.
    """
    tickers = set(positions) | set(target_tickers)
    return any(
        asset_classes.get(ticker, AssetClass.EQUITY) == AssetClass.CRYPTO
        for ticker in tickers
    )


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
    broker: Broker,
    scope: str = AssetScope.BOTH.value,
) -> list[str]:
    """Best-effort add of newly-proposed tickers to the universe (capped).

    Adds at most :data:`settings.AI_PORTFOLIO_MAX_NEW_ASSETS` tickers. Any add that
    fails (unknown ticker, market data unavailable, duplicate, not tradable on the
    brokerage, or a category outside the session's ``scope``) is logged and
    skipped — a rejected ticker is not added and (being out of scope) not traded.
    """
    allowed_categories = scope_categories(scope)
    added: list[str] = []
    for ticker in discovered[: settings.AI_PORTFOLIO_MAX_NEW_ASSETS]:
        try:
            assets_service.add_asset(
                session,
                ticker,
                provider,
                broker,
                allowed_categories=allowed_categories,
            )
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
    ledger: list[SessionPosition],
    broker: Broker,
    asset_classes: dict[str, AssetClass],
) -> list[dict[str, Any]]:
    """Build the agent's current-holdings context from the session's ledger.

    Quantity and cost basis come from the ledger (the source of truth); the
    current price is priced live via broker quotes. A ticker whose quote can't be
    fetched is included at a zero current price rather than aborting the run.
    """
    holdings: list[dict[str, Any]] = []
    for entry in ledger:
        if not entry.quantity:
            continue
        cost = entry.avg_cost or 0.0
        cls = asset_classes.get(entry.ticker, AssetClass.EQUITY)
        try:
            quote = broker.get_quote(entry.ticker, cls)
            current = quote.last or quote.ask or 0.0
        except Exception as exc:  # noqa: BLE001 - pricing is best-effort context
            logger.warning("holdings context: no quote for %s: %s", entry.ticker, exc)
            current = 0.0
        holdings.append(
            {
                "ticker": entry.ticker,
                "side": "long",
                "quantity": entry.quantity,
                "avg_cost": cost,
                "current_price": current,
                "unrealized_pnl": (current - cost) * entry.quantity,
                "pnl_pct": (current / cost - 1) if cost > 0 else 0.0,
            }
        )
    return holdings


def _record_trades(
    session: Session,
    session_id: uuid.UUID,
    trade_results: list[TradeResult],
    *,
    signal_prefix: str,
    event_id: uuid.UUID,
) -> int:
    """Persist each executed trade + open its ledger entry; return the count.

    Build trades are opening buys, so each executed fill opens or increases the
    session's ledger entry at the filled price (the cost basis).
    """
    executed = 0
    for tr in trade_results:
        if not tr.executed:
            continue
        side = _order_action(tr.side)
        paper_service.record_trade(
            session,
            session_id=session_id,
            ticker=tr.ticker,
            side=side,
            quantity=tr.shares,
            price=tr.price or 0.0,
            signal_type=f"{signal_prefix}_{tr.side}",
            order_id=tr.order_id,
            order_status=tr.order_status,
            filled_price=tr.filled_price,
            ai_portfolio_event_id=event_id,
        )
        paper_service.apply_fill_to_ledger(
            session,
            session_id=session_id,
            ticker=tr.ticker,
            side=side,
            shares=tr.shares,
            price=tr.filled_price or tr.price or 0.0,
        )
        executed += 1
    return executed


def _apply_rebalance_trades(
    session: Session,
    session_id: uuid.UUID,
    trade_results: list[TradeResult],
    *,
    event_id: uuid.UUID,
    signal_prefix: str = "ai_rebalance",
) -> tuple[int, float]:
    """Record rebalance trades + closed positions; return (executed, realized_pnl).

    Every executed fill updates the session's open-position ledger. Sells (side
    ``"sell"``) that reduce or close a long record a closed position for the sold
    quantity, using the ledger entry's weighted-average cost as the entry price and
    its opened date as the entry date — read *before* the sell decrements the
    ledger. The end-state ticker list is derived from the AI targets by the caller,
    so no add/remove bookkeeping is done here. ``signal_prefix`` tags the recorded
    trades (``"ai_rebalance"`` for a rebalance, ``"ai_close"`` for a full
    liquidation).
    """
    executed = 0
    realized_pnl_total = 0.0
    now = datetime.now(tz=UTC)

    for tr in trade_results:
        if not tr.executed:
            continue
        side = _order_action(tr.side)
        fill_price = tr.filled_price or tr.price or 0.0
        paper_service.record_trade(
            session,
            session_id=session_id,
            ticker=tr.ticker,
            side=side,
            quantity=tr.shares,
            price=tr.price or 0.0,
            signal_type=f"{signal_prefix}_{tr.side}",
            order_id=tr.order_id,
            order_status=tr.order_status,
            filled_price=tr.filled_price,
            ai_portfolio_event_id=event_id,
        )
        executed += 1

        # A sell reduces/closes an existing long; record realized P&L from the
        # ledger basis, captured before the fill decrements the entry below.
        if tr.side == "sell":
            basis = paper_service.get_position_entry_basis(
                session, session_id, tr.ticker
            )
            if basis is not None:
                entry_price, entry_date = basis
                exit_price = fill_price or entry_price
                closed = paper_service.record_closed_position(
                    session,
                    session_id=session_id,
                    ticker=tr.ticker,
                    quantity=tr.shares,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    entry_date=entry_date,
                    exit_date=now,
                    ai_portfolio_event_id=event_id,
                )
                realized_pnl_total += closed.realized_pnl

        paper_service.apply_fill_to_ledger(
            session,
            session_id=session_id,
            ticker=tr.ticker,
            side=side,
            shares=tr.shares,
            price=fill_price,
        )

    return executed, realized_pnl_total


def _finish_event(
    session: Session,
    event: AIPortfolioEvent,
    status: EventStatus,
    *,
    result_payload: dict[str, Any] | None,
    actions_taken: list[dict[str, Any]],
    duration_ms: int,
    research: list[dict[str, Any]] | None = None,
) -> None:
    event.status = status.value
    event.result_payload = result_payload
    event.actions_taken = actions_taken
    event.duration_ms = duration_ms
    if research:
        event.research = research
    session.commit()


def _fail_event(
    session: Session,
    event_id: uuid.UUID,
    error: str,
    duration_ms: int,
    research: list[dict[str, Any]] | None = None,
) -> None:
    """Best-effort transition of an event to ``failed`` with a reason.

    Any research captured before the failure is persisted so a failed run is still
    reviewable.
    """
    event = session.get(AIPortfolioEvent, event_id)
    if event is None:
        return
    event.status = EventStatus.FAILED.value
    event.error = error
    event.duration_ms = duration_ms
    if research:
        event.research = research
    session.commit()


def _elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
