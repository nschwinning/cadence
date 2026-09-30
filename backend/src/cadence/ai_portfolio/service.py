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
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agents.exceptions import MaxTurnsExceeded
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cadence.agents.tools import record_web_searches
from cadence.ai_portfolio.agent import AIPortfolioAgent, GuardrailInstruction
from cadence.ai_portfolio.constants import (
    AI_STRATEGY_KEY,
    TREND_PROMPT_VERSION,
    EventStatus,
    EventType,
)
from cadence.ai_portfolio.errors import (
    AIPortfolioValidationError,
    EventNotFoundError,
    RebalancePromptNotFoundError,
    SessionNotEligibleError,
)
from cadence.ai_portfolio.executor import (
    AIPortfolioExecutor,
    GuardrailCaps,
    TradeResult,
)
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
from cadence.paper_trading.benchmark import (
    benchmark_return_fraction,
    load_benchmark_series,
)
from cadence.paper_trading.constants import (
    STOP_LOSS_RUN_TRIGGER,
    STOP_LOSS_SIGNAL_TYPE,
    TERMINAL_ORDER_STATUSES,
    Benchmark,
    RunStatus,
    ScheduleMode,
    SessionStatus,
    benchmark_display_name,
)
from cadence.paper_trading.models import PaperTradingSession, SessionPosition
from cadence.portfolios import service as portfolios_service
from cadence.portfolios.constants import PortfolioSource, RiskProfile
from cadence.technical_indicators import service as ti_service
from cadence.technical_indicators.models import TechnicalIndicator
from cadence.utils.name_generator import generate_unique_name

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
    benchmark: str = settings.DEFAULT_BENCHMARK
    use_technical_indicators: bool = False
    stop_loss_enabled: bool = False
    stop_loss_pct: float | None = None
    risk_guardrails_enabled: bool = False
    max_allocation_pct: float | None = None
    max_asset_class_pct: float | None = None
    min_positions: int | None = None
    max_invested_pct: float | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "allocated_capital": self.allocated_capital,
            "risk_profile": self.risk_profile,
            "asset_types": self.asset_types,
            "daily_rebalancing": self.daily_rebalancing,
            "benchmark": self.benchmark,
            "use_technical_indicators": self.use_technical_indicators,
            "stop_loss_enabled": self.stop_loss_enabled,
            "stop_loss_pct": self.stop_loss_pct,
            "risk_guardrails_enabled": self.risk_guardrails_enabled,
            "max_allocation_pct": self.max_allocation_pct,
            "max_asset_class_pct": self.max_asset_class_pct,
            "min_positions": self.min_positions,
            "max_invested_pct": self.max_invested_pct,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> AIBuildParams:
        raw_pct = payload.get("stop_loss_pct")
        max_asset = payload.get("max_allocation_pct")
        max_class = payload.get("max_asset_class_pct")
        min_pos = payload.get("min_positions")
        max_inv = payload.get("max_invested_pct")
        return cls(
            allocated_capital=float(payload.get("allocated_capital", 10000.0)),
            risk_profile=str(payload.get("risk_profile", "balanced")),
            asset_types=str(payload.get("asset_types", AssetScope.BOTH.value)),
            daily_rebalancing=bool(payload.get("daily_rebalancing", False)),
            benchmark=str(payload.get("benchmark", settings.DEFAULT_BENCHMARK)),
            use_technical_indicators=bool(
                payload.get("use_technical_indicators", False)
            ),
            stop_loss_enabled=bool(payload.get("stop_loss_enabled", False)),
            stop_loss_pct=None if raw_pct is None else float(raw_pct),
            risk_guardrails_enabled=bool(
                payload.get("risk_guardrails_enabled", False)
            ),
            max_allocation_pct=None if max_asset is None else float(max_asset),
            max_asset_class_pct=None if max_class is None else float(max_class),
            min_positions=None if min_pos is None else int(min_pos),
            max_invested_pct=None if max_inv is None else float(max_inv),
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
    session: Session, session_id: uuid.UUID, *, limit: int = 20, offset: int = 0
) -> list[AIPortfolioEvent]:
    """Return a session's AI events (build + rebalances), newest first.

    Paginated via ``limit``/``offset`` (pair with :func:`count_session_events`).
    """
    stmt = (
        select(AIPortfolioEvent)
        .where(AIPortfolioEvent.session_id == session_id)
        .order_by(AIPortfolioEvent.created_at.desc(), AIPortfolioEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars())


def count_session_events(session: Session, session_id: uuid.UUID) -> int:
    """Count a session's AI events."""
    stmt = (
        select(func.count())
        .select_from(AIPortfolioEvent)
        .where(AIPortfolioEvent.session_id == session_id)
    )
    return session.execute(stmt).scalar_one()


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


def build_orders_settled(
    session: Session, broker: Broker, session_row: PaperTradingSession
) -> bool:
    """Return whether a session's initial build orders have all settled.

    A freshly-built session is not ready for daily rebalancing until the broker
    orders its build placed have all reached a terminal state — filled, or
    cancelled/rejected (a cancelled/rejected order will never fill, so it does not
    keep the session waiting). Readiness is judged from the *broker's* fill status,
    not the optimistic local ledger: the session's non-terminal orders are first
    reconciled against the broker (reusing
    :func:`paper_service.reconcile_session_orders`) so the recorded status is fresh
    even when the separate reconcile cron has not run first.

    A session whose build placed no orders that need to settle — an all-cash build,
    a build with no recorded build event, or one whose orders have already settled
    (for example under an immediate-fill broker) — is ready immediately, so this
    gate can never permanently strand a session.

    Fails safe: if reconciliation raises, the session is reported not ready
    (deferred to a later trigger) rather than rebalanced on unverified state.
    """
    metadata = session_row.session_metadata or {}
    raw_build_event_id = metadata.get("build_event_id")
    if raw_build_event_id is None:
        return True  # No build event recorded — nothing to wait on.
    try:
        build_event_id = uuid.UUID(str(raw_build_event_id))
    except (ValueError, TypeError):
        return True

    try:
        paper_service.reconcile_session_orders(session, broker, session_row.id)
    except Exception:  # Fail safe toward not trading on unverified state.
        logger.warning(
            "build-order readiness: reconcile failed for session %s; deferring",
            session_row.id,
            exc_info=True,
        )
        return False

    build_trades = paper_service.get_trades_by_event(session, build_event_id)
    for trade in build_trades:
        if trade.order_id is None:
            continue  # No broker order to track — nothing to wait on.
        if trade.order_status not in TERMINAL_ORDER_STATUSES:
            return False
    return True


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

    # Bound at ``with`` entry so any research/trend context captured before a
    # mid-run failure is still persisted on the (failed) event.
    research: list[dict[str, Any]] = []
    trend_context: dict[str, Any] | None = None
    try:
        params = AIBuildParams.from_payload(event.request_payload or {})
        allowed_categories = scope_categories(params.asset_types)
        universe = assets_service.list_assets(
            session, categories=[c.value for c in allowed_categories]
        )
        # The trend gate and its per-run context apply only when this build opted
        # into the technical-indicator trend strategy AND the active (highest)
        # prompt version is the trend strategy (i.e. after the v3 migration). When
        # the build opts out — the default — or the active prompt predates the trend
        # strategy, the build stays ungated and records no trend context.
        active_prompt = get_active_rebalance_prompt(session)
        gating_enabled = (
            params.use_technical_indicators
            and active_prompt.version >= TREND_PROMPT_VERSION
        )
        snapshots = (
            ti_service.get_latest_snapshots(
                session, [asset.id for asset in universe]
            )
            if gating_enabled
            else {}
        )
        candidates, dropped_candidates = _candidates_from_universe(
            universe, snapshots, apply_gate=gating_enabled
        )
        if gating_enabled:
            trend_context = {
                "dropped_candidates": dropped_candidates,
                "candidates": [
                    {"ticker": c["ticker"], "indicators": c["indicators"]}
                    for c in candidates
                ],
                "holdings": [],
            }

        build_guardrails = _guardrail_instruction(
            enabled=params.risk_guardrails_enabled,
            max_asset_pct=params.max_allocation_pct,
            max_asset_class_pct=params.max_asset_class_pct,
            min_positions=params.min_positions,
            max_invested_pct=params.max_invested_pct,
        )
        with record_web_searches() as research:
            result = agent.build(
                candidates=candidates,
                risk_profile=params.risk_profile,
                guardrails=build_guardrails,
            )
        agent_output = result.model_dump(mode="json")

        stock_tickers = _normalize_tickers([s.ticker for s in result.stocks])
        universe_tickers = {a.ticker for a in universe}
        discovered = [t for t in stock_tickers if t not in universe_tickers]
        if gating_enabled:
            # A discovered ticker that already has a stored snapshot failing the
            # gate is dropped from the candidate set; genuinely new tickers (no
            # snapshot) are still added and traded.
            discovered, discovered_dropped = _gate_discovered(session, discovered)
            if trend_context is not None:
                trend_context["dropped_candidates"].extend(discovered_dropped)
        _add_discovered_assets(
            session, discovered, provider, broker, scope=params.asset_types
        )

        # The AI names every build generically (e.g. "AI Growth"), so portfolios
        # collide and their sessions become indistinguishable. Generate a distinct,
        # human-friendly name instead; the AI's thesis is still kept as the
        # description.
        portfolio_name = generate_unique_name(
            risk_profile=params.risk_profile,
            existing_names=portfolios_service.list_portfolio_names(session),
        )
        # The per-asset guardrail cap repurposes ``max_allocation_pct`` (a no-op
        # 1.0 when guardrails are off) so both the portfolio and session freeze it.
        per_asset_cap = (
            params.max_allocation_pct
            if params.risk_guardrails_enabled
            and params.max_allocation_pct is not None
            else 1.0
        )
        portfolio = portfolios_service.create_portfolio(
            session,
            name=portfolio_name,
            stocks=stock_tickers,
            source=PortfolioSource.AI_MANAGED,
            description=result.overall_thesis[:500],
            risk_profile=_risk_profile(params.risk_profile),
            max_allocation_pct=per_asset_cap,
            source_run_id=str(event.id),
        )

        schedule_mode = (
            ScheduleMode.DAILY_REBALANCING
            if params.daily_rebalancing
            else ScheduleMode.MANUAL
        )
        # Freeze the currently active rebalance-prompt version onto the session so
        # every rebalance for it uses this version, regardless of later prompt edits.
        session_row = paper_service.create_session(
            session,
            portfolio_id=portfolio.id,
            strategy_key=AI_STRATEGY_KEY,
            rebalance_prompt_version=active_prompt.version,
            allocated_capital=params.allocated_capital,
            max_allocation_pct=portfolio.max_allocation_pct,
            schedule_mode=schedule_mode,
            benchmark=Benchmark(params.benchmark),
            use_technical_indicators=params.use_technical_indicators,
            stop_loss_enabled=params.stop_loss_enabled,
            stop_loss_pct=params.stop_loss_pct,
            risk_guardrails_enabled=params.risk_guardrails_enabled,
            max_asset_class_pct=params.max_asset_class_pct,
            min_positions=params.min_positions,
            max_invested_pct=params.max_invested_pct,
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

        caps = _guardrail_caps(
            enabled=params.risk_guardrails_enabled,
            max_asset_pct=params.max_allocation_pct,
            max_asset_class_pct=params.max_asset_class_pct,
            max_invested_pct=params.max_invested_pct,
        )
        executor = AIPortfolioExecutor(broker, params.allocated_capital)
        trade_results = executor.execute_build(
            result.stocks, asset_classes=asset_classes, caps=caps
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
            ai_portfolio_event_id=event.id,
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
            trend_context=trend_context,
            run_stats=_build_run_stats(
                trade_results=trade_results,
                executed=executed,
                all_executed=all_executed,
                trend_context=trend_context,
                guardrail_observations=_min_positions_observation(
                    build_guardrails,
                    sum(1 for s in result.stocks if s.allocation_pct > 0),
                ),
            ),
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
            _humanize_failure(exc),
            _elapsed_ms(t0),
            research=research,
            trend_context=trend_context,
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
    # Assembled at the candidate/holdings seam so a mid-run failure keeps it; stays
    # null on the skip path and for sessions frozen to a pre-trend prompt version.
    trend_context: dict[str, Any] | None = None
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
                ai_portfolio_event_id=event.id,
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

        # The trend gate and its per-run context apply only when this session opted
        # into the technical-indicator trend strategy at build time AND is frozen to
        # the trend prompt version (or later). Sessions that opted out (the default,
        # including every session built before the opt-in existed) or on an earlier
        # (pre-trend) prompt version keep their original ungated behaviour and record
        # no trend context.
        gating_enabled = (
            session_row.use_technical_indicators
            and session_row.rebalance_prompt_version >= TREND_PROMPT_VERSION
        )

        # A freshly stopped-out position is quarantined for a cooldown window so the
        # agent cannot immediately re-buy it. Exclude quarantined tickers the session
        # does not currently hold (regardless of the trend opt-in); once the
        # quarantine expires the ticker becomes a candidate again. Held tickers are
        # never excluded so the agent can still decide to keep or sell them.
        held_tickers = {entry.ticker for entry in ledger if entry.quantity}
        quarantined_tickers = paper_service.list_active_quarantined_tickers(
            session, session_id
        )

        def _is_quarantined(ticker: str) -> bool:
            return ticker in quarantined_tickers and ticker not in held_tickers

        # Candidates are restricted to the session's asset scope; the full universe
        # (above) still backs the class map so held positions stay classified.
        scoped_universe = [
            asset
            for asset in universe
            if asset.category in allowed_categories and not _is_quarantined(asset.ticker)
        ]
        candidate_snapshots = (
            ti_service.get_latest_snapshots(
                session, [asset.id for asset in scoped_universe]
            )
            if gating_enabled
            else {}
        )
        candidates, dropped_candidates = _candidates_from_universe(
            scoped_universe, candidate_snapshots, apply_gate=gating_enabled
        )
        holding_snapshots = (
            _snapshots_by_ticker(
                session, [entry.ticker for entry in ledger if entry.quantity]
            )
            if gating_enabled
            else None
        )
        holdings = _build_holdings(
            ledger, broker, asset_classes, holding_snapshots
        )
        if gating_enabled:
            trend_context = {
                "dropped_candidates": dropped_candidates,
                "candidates": [
                    {"ticker": c["ticker"], "indicators": c["indicators"]}
                    for c in candidates
                ],
                "holdings": [
                    {
                        "ticker": h["ticker"],
                        "indicators": h["indicators"],
                        "reversal_flags": h["reversal_flags"],
                    }
                    for h in holdings
                ],
            }
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
        rebalance_guardrails = _guardrail_instruction(
            enabled=bool(session_row.risk_guardrails_enabled),
            max_asset_pct=session_row.max_allocation_pct,
            max_asset_class_pct=session_row.max_asset_class_pct,
            min_positions=session_row.min_positions,
            max_invested_pct=session_row.max_invested_pct,
        )
        with record_web_searches() as research:
            result = agent.rebalance(
                holdings=holdings,
                account_summary=account_summary,
                candidates=candidates,
                risk_profile=risk_profile,
                instructions=prompt.instructions,
                input_template=prompt.input_template,
                guardrails=rebalance_guardrails,
            )
        agent_output = result.model_dump(mode="json")

        # Best-effort add of any discovered target ticker not yet in the universe;
        # out-of-scope discoveries are rejected inside ``_add_discovered_assets``.
        universe_tickers = {a.ticker for a in universe}
        target_tickers = _normalize_tickers(
            [t.ticker for t in result.target_allocations]
        )
        discovered = [
            t
            for t in target_tickers
            if t not in universe_tickers and not _is_quarantined(t)
        ]
        if gating_enabled:
            # A discovered ticker that already has a stored snapshot failing the
            # gate is dropped; genuinely new tickers (no snapshot) are still added.
            discovered, discovered_dropped = _gate_discovered(session, discovered)
            if trend_context is not None:
                trend_context["dropped_candidates"].extend(discovered_dropped)
        _add_discovered_assets(
            session, discovered, provider, broker, scope=asset_scope
        )

        # Rebuild the class map so any discovered crypto target is classified.
        asset_classes = _asset_class_map(assets_service.list_assets(session))

        # Read the guardrail config back off the frozen session row; a disabled or
        # pre-migration session yields no caps and the executor stays normalize-only.
        caps = _guardrail_caps(
            enabled=bool(session_row.risk_guardrails_enabled),
            max_asset_pct=session_row.max_allocation_pct,
            max_asset_class_pct=session_row.max_asset_class_pct,
            max_invested_pct=session_row.max_invested_pct,
        )
        executor = AIPortfolioExecutor(broker, session_row.allocated_capital)
        trade_results = executor.execute_rebalance(
            targets=result.target_allocations,
            current_positions=positions,
            asset_classes=asset_classes,
            market_open=market_open,
            caps=caps,
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
            ai_portfolio_event_id=event.id,
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
            trend_context=trend_context,
            run_stats=_build_run_stats(
                trade_results=trade_results,
                executed=executed,
                all_executed=all_executed,
                realized_pnl=realized_pnl,
                account_summary=account_summary,
                trend_context=trend_context,
                guardrail_observations=_min_positions_observation(
                    rebalance_guardrails,
                    sum(
                        1
                        for t in result.target_allocations
                        if t.allocation_pct > 0
                    ),
                ),
            ),
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
        reason = _humanize_failure(exc)
        _fail_event(
            session,
            event_id,
            reason,
            _elapsed_ms(t0),
            research=research,
            trend_context=trend_context,
        )
        if notifier is not None:
            _notify_safely(
                notifier,
                title="Cadence: daily rebalance failed",
                message=f"Rebalance {event_id} failed: {reason}",
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
    ``as_of`` (today in the market-close timezone when omitted). Sends **one push
    per session** (titled by its portfolio name) carrying that session's value and
    day P&L, headline KPIs (total return, realized/unrealized P&L, fees, Sharpe),
    its benchmark comparison, and its own best/worst holding. Delivery is
    best-effort — a notifier failure never fails the job (see
    :func:`_notify_safely`). Returns the ids of the sessions snapshotted.
    """
    if as_of is None:
        as_of = datetime.now(tz=_SNAPSHOT_TZ).date()

    sessions = paper_service.list_sessions(
        session, status=SessionStatus.ACTIVE, limit=500
    )
    targets = [s for s in sessions if s.strategy_key == AI_STRATEGY_KEY]

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


# --------------------------------------------------------------------------- #
# Stop-loss scan
# --------------------------------------------------------------------------- #


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
    (the flat transaction cost is charged at ``record_trade``), a ``stop_loss``
    session run, and a cooldown quarantine, and fires a best-effort notification.
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


def _stop_loss_message(
    label: str,
    ticker: str,
    shares: float,
    exit_price: float,
    realized_pnl: float,
) -> str:
    """Build the push body for a single stop-out."""
    return (
        f"{label}: stop-loss triggered\n"
        f"SELL {shares:g} {ticker} @ ${exit_price:,.2f}\n"
        f"Realized P&L: ${realized_pnl:,.2f}"
    )


def _signed_money(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}${abs(value):,.2f}"


def _signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}{abs(value) * 100:.2f}%"


def _sharpe_text(sharpe: float | None) -> str:
    """Signed Sharpe to 2dp, or an em dash until enough history exists."""
    return f"{sharpe:+.2f}" if sharpe is not None else "—"


def _session_snapshot_message(
    snapshot: Any,
    kpis: Any,
    benchmark_suffix: str | None,
    holdings: list[tuple[str, float]],
) -> str:
    """Build one session's daily push body.

    The portfolio name lives in the push title, so the body leads with the day's
    value + P&L, then headline KPIs (total return, realized/unrealized P&L, fees,
    Sharpe), the benchmark comparison (when available), and the session's own
    best/worst holding (when it holds anything).
    """
    lines = [
        (
            f"${snapshot.total_value:,.2f} today "
            f"({_signed_money(snapshot.daily_pnl)}, "
            f"{_signed_pct(snapshot.daily_pnl_pct)})"
        ),
        (
            f"Total return: {_signed_money(kpis.total_return)} "
            f"({_signed_pct(kpis.total_return_pct)})"
        ),
        (
            f"Realized {_signed_money(kpis.realised_pnl)} · "
            f"Unrealized {_signed_money(kpis.unrealised_pnl)} · "
            f"Fees ${kpis.total_fees:,.2f}"
        ),
        f"Sharpe: {_sharpe_text(kpis.sharpe_ratio)}",
    ]
    if benchmark_suffix is not None:
        lines.append(benchmark_suffix)
    best_worst = _best_worst_line(holdings)
    if best_worst is not None:
        lines.append(best_worst)
    return "\n".join(lines)


def _benchmark_suffix(
    session: Session,
    session_row: Any,
    snapshot: Any,
    *,
    as_of: date,
) -> str | None:
    """Benchmark comparison suffix for a session's report line, or ``None``.

    Computes the session's benchmark buy-and-hold return over the period (from its
    first snapshot date to ``as_of``, using stored prices) and the excess return
    (session total return − benchmark return). Returns ``None`` when the session has
    no snapshots or the benchmark lacks usable stored prices, so the caller omits
    the suffix.
    """
    snapshots = paper_service.list_value_snapshots(
        session, session_id=session_row.id
    )
    if not snapshots:
        return None
    series = load_benchmark_series(session, session_row.benchmark)
    benchmark_return = benchmark_return_fraction(
        series, start_date=snapshots[0].snapshot_date, as_of=as_of
    )
    if benchmark_return is None:
        return None
    allocated = session_row.allocated_capital
    total_return_pct = (
        (snapshot.total_value - allocated) / allocated if allocated > 0 else 0.0
    )
    excess = total_return_pct - benchmark_return
    name = benchmark_display_name(Benchmark(session_row.benchmark))
    return (
        f"vs {name}: {_signed_pct(benchmark_return)} "
        f"(excess {_signed_pct(excess)})"
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


def _guardrail_caps(
    *,
    enabled: bool,
    max_asset_pct: float | None,
    max_asset_class_pct: float | None,
    max_invested_pct: float | None,
) -> GuardrailCaps | None:
    """Build :class:`GuardrailCaps` from a frozen guardrail config, or ``None``.

    Returns ``None`` when guardrails are disabled (or the frozen config predates
    the feature) so the executor keeps its normalize-only path. A missing cap
    (``None`` while enabled) is treated as no-op (1.0) for that dimension.
    """
    if not enabled:
        return None
    return GuardrailCaps(
        max_per_asset=max_asset_pct if max_asset_pct is not None else 1.0,
        max_per_class=(
            max_asset_class_pct if max_asset_class_pct is not None else 1.0
        ),
        max_invested=max_invested_pct if max_invested_pct is not None else 1.0,
    )


def _guardrail_instruction(
    *,
    enabled: bool,
    max_asset_pct: float | None,
    max_asset_class_pct: float | None,
    min_positions: int | None,
    max_invested_pct: float | None,
) -> GuardrailInstruction | None:
    """Build the advisory :class:`GuardrailInstruction` told to the AI, or ``None``.

    Returns ``None`` when guardrails are disabled so the prompt carries no
    guardrail block. Includes ``min_positions`` (which the deterministic clamp
    cannot enforce) so the AI can plan to meet the diversification floor.
    """
    if not enabled:
        return None
    return GuardrailInstruction(
        max_per_asset=max_asset_pct if max_asset_pct is not None else 1.0,
        max_per_class=(
            max_asset_class_pct if max_asset_class_pct is not None else 1.0
        ),
        min_positions=min_positions if min_positions is not None else 1,
        max_invested=max_invested_pct if max_invested_pct is not None else 1.0,
    )


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


def _indicator_annotation(snap: TechnicalIndicator) -> dict[str, Any]:
    """The trend-indicator values handed to the AI for a candidate or holding."""
    return {
        "trading_date": snap.trading_date.isoformat() if snap.trading_date else None,
        "close": snap.close,
        "sma_50": snap.sma_50,
        "sma_200": snap.sma_200,
        "close_sma200": snap.close_sma200,
        "sma50_sma200": snap.sma50_sma200,
        "sma200_slope": snap.sma200_slope,
        "ema_20": snap.ema_20,
        "macd_line": snap.macd_line,
        "macd_signal": snap.macd_signal,
        "macd_hist": snap.macd_hist,
        "rsi_14": snap.rsi_14,
        "roc_120": snap.roc_120,
        "obv": snap.obv,
        "obv_change_20d": snap.obv_change_20d,
        "vol_ratio_50": snap.vol_ratio_50,
        "dist_high_52w": snap.dist_high_52w,
        "drawdown_from_max": snap.drawdown_from_max,
        "hvol_20": snap.hvol_20,
        "bb_pctb": snap.bb_pctb,
        "bb_width": snap.bb_width,
        "gate_pass": snap.gate_pass,
        "regime_pass": snap.regime_pass,
        "momentum_pass": snap.momentum_pass,
        "obv_rising": snap.obv_rising,
    }


def _reversal_annotation(snap: TechnicalIndicator) -> dict[str, Any]:
    """The deterministic reversal flags handed to the AI for a holding."""
    return {
        "macd_hist_rollover": snap.rev_macd_hist_rollover,
        "rsi_rollover": snap.rev_rsi_rollover,
        "return_decel": snap.rev_return_decel,
        "obv_price_divergence": snap.rev_obv_price_divergence,
        "sma200_slope_flattening": snap.rev_sma200_slope_flattening,
    }


def _gate_failure_reason(snap: TechnicalIndicator) -> str:
    """Name the gate condition a dropped candidate failed (for the run context)."""
    if not snap.regime_pass:
        return "regime not confirmed (close>SMA200, SMA50>SMA200, SMA200 slope>=0)"
    if not snap.momentum_pass:
        return "momentum not confirmed (MACD hist>0, RSI14>50, ROC120>0)"
    return "trend gate failed"


def _candidates_from_universe(
    assets: list[Asset],
    snapshots: dict[int, TechnicalIndicator],
    *,
    apply_gate: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the candidate records the agent reasons over from the universe.

    Returns ``(candidates, dropped)``. When ``apply_gate`` is true (trend
    strategy), each in-scope asset is kept only if it has a stored snapshot whose
    uptrend gate passes; survivors are annotated with their trend indicators, and
    assets that fail the gate or lack a snapshot are dropped from the candidate set
    (never shown to the AI) and returned in ``dropped`` with the reason. When
    ``apply_gate`` is false (pre-trend prompt version), every asset is a candidate
    with no indicator annotation and nothing is dropped (original behaviour).
    """
    candidates: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for asset in assets:
        base = {
            "ticker": asset.ticker,
            "company_name": asset.name or asset.ticker,
            "sector": asset.sector or "unknown",
            "category": asset.category,
            "is_eligible": asset.is_eligible,
        }
        if not apply_gate:
            candidates.append(base)
            continue
        snap = snapshots.get(asset.id)
        if snap is None:
            dropped.append({"ticker": asset.ticker, "reason": "no snapshot"})
            continue
        if not snap.gate_pass:
            dropped.append(
                {"ticker": asset.ticker, "reason": _gate_failure_reason(snap)}
            )
            continue
        candidates.append({**base, "indicators": _indicator_annotation(snap)})
    return candidates, dropped


def _snapshots_by_ticker(
    session: Session, tickers: list[str]
) -> dict[str, TechnicalIndicator]:
    """Resolve the latest stored snapshot for each ticker, keyed by ticker."""
    if not tickers:
        return {}
    id_to_ticker = {
        asset.id: asset.ticker
        for asset in session.execute(
            select(Asset).where(Asset.ticker.in_(tickers))
        ).scalars()
    }
    snaps = ti_service.get_latest_snapshots(session, list(id_to_ticker))
    return {id_to_ticker[asset_id]: snap for asset_id, snap in snaps.items()}


def _gate_discovered(
    session: Session, discovered: list[str]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Drop discovered tickers whose stored snapshot already fails the trend gate.

    A discovered ticker with no stored snapshot is kept — a genuinely new asset is
    still added and traded, and will be gated as a normal candidate in later runs
    once the nightly job computes its snapshot. One that already has a stored
    snapshot failing the gate is dropped from the candidate set. Returns the
    surviving tickers and the dropped records (ticker + reason).
    """
    if not discovered:
        return [], []
    snaps = _snapshots_by_ticker(session, discovered)
    survivors: list[str] = []
    dropped: list[dict[str, Any]] = []
    for ticker in discovered:
        snap = snaps.get(ticker)
        if snap is not None and not snap.gate_pass:
            dropped.append({"ticker": ticker, "reason": _gate_failure_reason(snap)})
            continue
        survivors.append(ticker)
    return survivors, dropped


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
    snapshots: dict[str, TechnicalIndicator] | None = None,
) -> list[dict[str, Any]]:
    """Build the agent's current-holdings context from the session's ledger.

    Quantity and cost basis come from the ledger (the source of truth); the
    current price is priced live via broker quotes. A ticker whose quote can't be
    fetched is included at a zero current price rather than aborting the run.

    When ``snapshots`` is provided (trend strategy), each holding also carries its
    full indicator set and deterministic reversal flags so the AI can decide
    sell/trim/hold — there is no hard exit. A holding without a stored snapshot
    carries ``None`` for both. When ``snapshots`` is ``None`` (pre-trend prompt
    version) no technical context is attached (original behaviour).
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
        holding: dict[str, Any] = {
            "ticker": entry.ticker,
            "side": "long",
            "quantity": entry.quantity,
            "avg_cost": cost,
            "current_price": current,
            "unrealized_pnl": (current - cost) * entry.quantity,
            "pnl_pct": (current / cost - 1) if cost > 0 else 0.0,
        }
        if snapshots is not None:
            snap = snapshots.get(entry.ticker)
            holding["indicators"] = _indicator_annotation(snap) if snap else None
            holding["reversal_flags"] = _reversal_annotation(snap) if snap else None
        holdings.append(holding)
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
    trend_context: dict[str, Any] | None = None,
    run_stats: dict[str, Any] | None = None,
) -> None:
    event.status = status.value
    event.result_payload = result_payload
    event.actions_taken = actions_taken
    event.duration_ms = duration_ms
    if research:
        event.research = research
    if trend_context:
        event.trend_context = trend_context
    if run_stats:
        event.run_stats = run_stats
    session.commit()


def _fail_event(
    session: Session,
    event_id: uuid.UUID,
    error: str,
    duration_ms: int,
    research: list[dict[str, Any]] | None = None,
    trend_context: dict[str, Any] | None = None,
) -> None:
    """Best-effort transition of an event to ``failed`` with a reason.

    Any research/trend context captured before the failure is persisted so a failed
    run is still reviewable.
    """
    event = session.get(AIPortfolioEvent, event_id)
    if event is None:
        return
    event.status = EventStatus.FAILED.value
    event.error = error
    event.duration_ms = duration_ms
    if research:
        event.research = research
    if trend_context:
        event.trend_context = trend_context
    session.commit()


def _humanize_failure(exc: Exception) -> str:
    """Render an exception as a user-facing failure reason for the event row.

    Most exceptions carry a readable message, but the agents SDK's
    :class:`MaxTurnsExceeded` stringifies to a terse ``"Max turns (N) exceeded"``
    that means nothing to a portfolio owner. Translate it into an actionable
    sentence; everything else falls back to its message (or class name).
    """
    if isinstance(exc, MaxTurnsExceeded):
        return (
            f"The AI reached its step limit ({settings.AI_PORTFOLIO_MAX_TURNS} turns) "
            "before finishing — usually too many web searches or tool calls in one "
            "run. No changes were made. Please retry."
        )
    return str(exc) or exc.__class__.__name__


def _build_run_stats(
    *,
    trade_results: list[TradeResult],
    executed: int,
    all_executed: bool,
    realized_pnl: float | None = None,
    account_summary: dict[str, Any] | None = None,
    trend_context: dict[str, Any] | None = None,
    guardrail_observations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the machine-readable run-outcome blob for offline learning.

    Captures order counts, full per-trade details (including ``filled_price``,
    which ``actions_taken`` drops), the run's realized P&L and account/valuation
    snapshot where applicable, trend-gate counts derived from ``trend_context``,
    and any guardrail observations (e.g. the AI returning fewer holdings than the
    configured minimum). Deliberately not exposed via the API/UI (see
    ``AIPortfolioEvent.run_stats``).
    """
    stats: dict[str, Any] = {
        "orders": {
            "executed": executed,
            "skipped": len(trade_results) - executed,
            "total": len(trade_results),
            "all_executed": all_executed,
        },
        "trades": [tr.to_stats_dict() for tr in trade_results],
    }
    if realized_pnl is not None:
        stats["realized_pnl"] = realized_pnl
    if account_summary is not None:
        stats["account"] = account_summary
    if trend_context is not None:
        stats["gate"] = {
            "candidates": len(trend_context.get("candidates", [])),
            "dropped": len(trend_context.get("dropped_candidates", [])),
            "holdings": len(trend_context.get("holdings", [])),
        }
    if guardrail_observations:
        stats["guardrails"] = guardrail_observations
    return stats


def _min_positions_observation(
    guardrails: GuardrailInstruction | None, num_positions: int
) -> dict[str, Any] | None:
    """Return a min-positions guardrail observation when the AI under-diversified.

    Min positions is not enforced by fabricating holdings (see design D3); when
    the AI returns fewer positions than the configured minimum the shortfall is
    recorded here for offline learning and the run still succeeds. Returns
    ``None`` when guardrails are off or the minimum is met.
    """
    if guardrails is None:
        return None
    if num_positions >= guardrails.min_positions:
        return None
    return {
        "min_positions": {
            "required": guardrails.min_positions,
            "returned": num_positions,
            "shortfall": guardrails.min_positions - num_positions,
        }
    }


def _elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
