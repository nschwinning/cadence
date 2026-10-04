"""System-status router. Mounted under ``/api/v1``.

Exposes a single plain read (NOT cron-guarded) that live-probes each external
backend and reports its reachability + latency. The probe service isolates every
backend, so this endpoint always returns 200 with per-backend outcomes — one
unreachable backend never fails the others or the response. No secret value is
ever included in the payload (see :mod:`cadence.system.service`).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from cadence.api.schemas import SystemStatusRead
from cadence.system import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusRead)
def get_system_status() -> SystemStatusRead:
    """Return the live status of every connected external backend.

    Each backend is probed concurrently under a bounded per-probe timeout and
    reported as configured/reachable with its latency and a non-secret identifier
    (broker mode, provider name, model id). Always 200.
    """
    return SystemStatusRead.model_validate(service.get_system_status())
