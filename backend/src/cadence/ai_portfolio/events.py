"""Event-CRUD and session-eligibility queries for the AI-portfolio service.

Create/read the ``ai_portfolio_events`` rows that record each job's lifecycle, and
answer the small eligibility questions (build-order readiness, whether a session
involves or admits crypto) the routers and crons need before launching a job.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cadence.ai_portfolio._helpers import _asset_class_map, _involves_crypto
from cadence.ai_portfolio.constants import EventStatus, EventType
from cadence.ai_portfolio.errors import (
    AIPortfolioValidationError,
    EventNotFoundError,
)
from cadence.ai_portfolio.models import AIPortfolioEvent
from cadence.ai_portfolio.params import AIBuildParams
from cadence.assets import service as assets_service
from cadence.assets.category import AssetCategory, AssetScope, scope_categories
from cadence.broker.base import Broker
from cadence.broker.models import Position
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import TERMINAL_ORDER_STATUSES
from cadence.paper_trading.models import PaperTradingSession
from cadence.portfolios import service as portfolios_service

logger = logging.getLogger(__name__)


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


def session_involves_crypto(
    session: Session, session_row: PaperTradingSession
) -> bool:
    """Whether a session holds or currently targets any crypto.

    Used by the weekend crypto-only cron to skip sessions with no crypto sleeve
    *before* a job (and an AI event) is ever created — the same no-crypto condition
    the crypto-only run would otherwise short-circuit on. Mirrors the in-run
    ``any_crypto`` check: a session involves crypto iff any open position or any
    current portfolio target is classified crypto by the universe.
    """
    asset_classes = _asset_class_map(assets_service.list_assets(session))
    positions = {
        entry.ticker: Position(
            symbol=entry.ticker,
            quantity=entry.quantity,
            avg_cost=entry.avg_cost,
        )
        for entry in paper_service.list_open_positions(session, session_row.id)
    }
    portfolio = portfolios_service.get_portfolio(session, session_row.portfolio_id)
    return _involves_crypto(positions, portfolio.stocks, asset_classes)


def session_allows_crypto(session_row: PaperTradingSession) -> bool:
    """Whether a session's **configured** asset scope admits crypto.

    Reads ``asset_types`` off the session's ``session_metadata`` (the scope frozen
    at build, defaulting to :attr:`AssetScope.BOTH` for sessions built before an
    explicit scope existed) and returns ``True`` iff that scope includes crypto
    (scope is ``crypto`` or ``both``). Unlike :func:`session_involves_crypto` this
    needs no DB access and answers a different question — what the user *configured*
    rather than what the session currently *holds* — so weekend selection and the
    weekend P&L gate key off the user's intent, not transient holdings.
    """
    metadata = session_row.session_metadata or {}
    asset_scope = str(metadata.get("asset_types", AssetScope.BOTH.value))
    return AssetCategory.CRYPTO in scope_categories(asset_scope)
