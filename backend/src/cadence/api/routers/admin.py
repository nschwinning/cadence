"""Broker-account admin router. Mounted under ``/api/v1``.

``GET /admin/account`` is a plain read that always answers 200 — a broker failure is
reported in the payload (``broker_available=false``). ``POST /admin/flatten-orphans``
sells recomputed orphan quantities; it accepts a symbol (or none for all) but never a
quantity. Not cron-guarded: like stopping a bot, it is an operator action confirmed in
the UI.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from cadence.admin import service
from cadence.api.schemas import (
    AdminAccountRead,
    AdminFlattenOutcomeRead,
    AdminFlattenRequest,
    AdminFlattenResponse,
)
from cadence.broker import get_broker
from cadence.broker.base import Broker, BrokerError
from cadence.database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])

DbSession = Annotated[Session, Depends(get_db)]
BrokerDep = Annotated[Broker, Depends(get_broker)]


@router.get("/account", response_model=AdminAccountRead)
def get_account(db: DbSession, broker: BrokerDep) -> AdminAccountRead:
    """Live account figures, committed-cash check, open orders and positions comparison."""
    return AdminAccountRead.model_validate(service.account_overview(db, broker))


@router.post("/flatten-orphans", response_model=AdminFlattenResponse)
def flatten_orphans(
    payload: AdminFlattenRequest, db: DbSession, broker: BrokerDep
) -> AdminFlattenResponse:
    """Sell the orphan excess for one symbol, or for every orphan when none is given."""
    try:
        outcomes = service.flatten_orphans(db, broker, symbol=payload.symbol)
    except BrokerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc) or "Brokerage is unavailable",
        ) from exc
    return AdminFlattenResponse(
        outcomes=[AdminFlattenOutcomeRead.model_validate(o) for o in outcomes]
    )
