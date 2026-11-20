"""System-status router. Mounted under ``/api/v1``.

Exposes a single plain read (NOT cron-guarded) that live-probes each external
backend and reports its reachability + latency. The probe service isolates every
backend, so this endpoint always returns 200 with per-backend outcomes — one
unreachable backend never fails the others or the response. No secret value is
ever included in the payload (see :mod:`cadence.system.service`).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from cadence import environment
from cadence.accounts.service import CurrentAccount
from cadence.api.schemas import EnvironmentRead, MeRead, SystemStatusRead
from cadence.broker import Broker, BrokerError, get_broker
from cadence.system import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])
#: Account routes without the /system prefix (``GET /api/v1/me``).
me_router = APIRouter(tags=["account"])


@router.get("/status", response_model=SystemStatusRead)
def get_system_status() -> SystemStatusRead:
    """Return the live status of every connected external backend.

    Each backend is probed concurrently under a bounded per-probe timeout and
    reported as configured/reachable with its latency and a non-secret identifier
    (broker mode, provider name, model id). Always 200.
    """
    return SystemStatusRead.model_validate(service.get_system_status())


def optional_broker() -> Broker | None:
    """The configured broker, or ``None`` when it cannot be built (e.g. missing keys)."""
    try:
        return get_broker()
    except BrokerError:
        return None


@router.get("/environment", response_model=EnvironmentRead)
def get_environment(
    broker: Annotated[Broker | None, Depends(optional_broker)],
) -> EnvironmentRead:
    """Return this deployment's name, verified account mode and whether it may trade.

    The account mode comes from a read-only, cached broker probe; no key or account
    number is included. Always 200 (an unreachable broker reports ``unknown``).
    """
    return EnvironmentRead.model_validate(environment.resolve_environment(broker))


@me_router.get("/me", response_model=MeRead)
def get_me(account: CurrentAccount) -> MeRead:
    """The signed-in user's account (with authentication disabled: the legacy owner)."""
    return MeRead(user_id=account.user_id, username=account.username, is_admin=account.is_admin)
