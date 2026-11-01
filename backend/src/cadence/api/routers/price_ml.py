"""Price-ML router. Mounted under ``/api/v1``.

Exposes a single cron-guarded trigger that runs the price-ML precompute
synchronously over the whole universe and returns a summary. Guarded by the
shared ``X-Cron-Token`` header (empty config rejects all). Sequenced in
deployment after the technical-indicators cron so the precompute runs on the
freshest stored price history.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from cadence.api.cron_auth import require_valid_cron_token
from cadence.api.schemas import PriceMlRefreshRead
from cadence.database import get_db
from cadence.price_ml import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/price-ml", tags=["price-ml"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("/refresh", response_model=PriceMlRefreshRead)
def refresh_price_ml(
    db: DbSession,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> PriceMlRefreshRead:
    """Train-or-reuse the pooled model and store one signal row per eligible asset.

    Guarded by the ``X-Cron-Token`` header. Runs the precompute synchronously and
    returns a summary of the run. Sequenced after the technical-indicators cron.
    """
    summary = service.refresh_signals(db)
    return PriceMlRefreshRead.model_validate(summary)
