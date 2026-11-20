"""Ownership guards for routes that address an owned object by id.

Each guard is a route dependency (``dependencies=[ReadSession]`` …): it looks up the
owner of the object named in the path and applies :func:`ensure_can_read` (own data, or
any for an admin; otherwise 404) or :func:`ensure_can_act` (own data only; 404 for other
users, 403 for an admin). A guard does nothing when the object does not exist, so the
route still answers its own 404.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.accounts.service import CurrentAccount, ensure_can_act, ensure_can_read
from cadence.ai_portfolio.models import AIPortfolioEvent
from cadence.bot_orchestrator.models import BotOrchestrator, BotOrchestratorRun
from cadence.database import get_db
from cadence.paper_trading.models import PaperTradingSession
from cadence.portfolios.models import Portfolio
from cadence.strategy_bots.models import BotSession

DbSession = Annotated[Session, Depends(get_db)]


# Owner lookups ----------------------------------------------------------------------
def portfolio_owner(db: Session, portfolio_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(Portfolio.owner_user_id).where(Portfolio.id == portfolio_id)
    ).scalar_one_or_none()


def session_owner(db: Session, session_id: uuid.UUID) -> uuid.UUID | None:
    """The owner of a paper-trading session: its portfolio's owner."""
    return db.execute(
        select(Portfolio.owner_user_id)
        .join(PaperTradingSession, PaperTradingSession.portfolio_id == Portfolio.id)
        .where(PaperTradingSession.id == session_id)
    ).scalar_one_or_none()


def event_owner(db: Session, event_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(AIPortfolioEvent.owner_user_id).where(AIPortfolioEvent.id == event_id)
    ).scalar_one_or_none()


def bot_owner(db: Session, bot_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(BotSession.owner_user_id).where(BotSession.id == bot_id)
    ).scalar_one_or_none()


def orchestrator_owner(db: Session, orchestrator_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(BotOrchestrator.owner_user_id).where(BotOrchestrator.id == orchestrator_id)
    ).scalar_one_or_none()


def orchestrator_run_owner(db: Session, run_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(BotOrchestrator.owner_user_id)
        .join(BotOrchestratorRun, BotOrchestratorRun.orchestrator_id == BotOrchestrator.id)
        .where(BotOrchestratorRun.id == run_id)
    ).scalar_one_or_none()


# Guards (the path parameter names must match the routes') ------------------------------
def _read(owner: uuid.UUID | None, account: CurrentAccount) -> None:
    if owner is not None:
        ensure_can_read(account, owner)


def _act(owner: uuid.UUID | None, account: CurrentAccount) -> None:
    if owner is not None:
        ensure_can_act(account, owner)


def read_portfolio(portfolio_id: uuid.UUID, account: CurrentAccount, db: DbSession) -> None:
    _read(portfolio_owner(db, portfolio_id), account)


def act_portfolio(portfolio_id: uuid.UUID, account: CurrentAccount, db: DbSession) -> None:
    _act(portfolio_owner(db, portfolio_id), account)


def read_session(session_id: uuid.UUID, account: CurrentAccount, db: DbSession) -> None:
    _read(session_owner(db, session_id), account)


def act_session(session_id: uuid.UUID, account: CurrentAccount, db: DbSession) -> None:
    _act(session_owner(db, session_id), account)


def read_event(event_id: uuid.UUID, account: CurrentAccount, db: DbSession) -> None:
    _read(event_owner(db, event_id), account)


def read_bot(session_id: uuid.UUID, account: CurrentAccount, db: DbSession) -> None:
    _read(bot_owner(db, session_id), account)


def act_bot(session_id: uuid.UUID, account: CurrentAccount, db: DbSession) -> None:
    _act(bot_owner(db, session_id), account)


def read_orchestrator(orchestrator_id: uuid.UUID, account: CurrentAccount, db: DbSession) -> None:
    _read(orchestrator_owner(db, orchestrator_id), account)


def act_orchestrator(orchestrator_id: uuid.UUID, account: CurrentAccount, db: DbSession) -> None:
    _act(orchestrator_owner(db, orchestrator_id), account)


def read_orchestrator_run(run_id: uuid.UUID, account: CurrentAccount, db: DbSession) -> None:
    _read(orchestrator_run_owner(db, run_id), account)


ReadPortfolio = Depends(read_portfolio)
ActPortfolio = Depends(act_portfolio)
ReadSession = Depends(read_session)
ActSession = Depends(act_session)
ReadEvent = Depends(read_event)
ReadBot = Depends(read_bot)
ActBot = Depends(act_bot)
ReadOrchestrator = Depends(read_orchestrator)
ActOrchestrator = Depends(act_orchestrator)
ReadOrchestratorRun = Depends(read_orchestrator_run)
