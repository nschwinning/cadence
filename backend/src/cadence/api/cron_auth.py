"""Shared cron-token authentication dependency.

Cron-triggered endpoints (daily rebalance, snapshot, technical indicators, the
quarterly fundamentals refresh, …) are guarded by a single shared secret sent in
the ``X-Cron-Token`` header. The dependency lives here — rather than on any one
router — so every router can depend on it without importing another router (which
would create an import cycle).
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

from cadence.config import settings


def require_valid_cron_token(
    x_cron_token: Annotated[str | None, Header()] = None,
) -> None:
    """Reject the request unless ``X-Cron-Token`` matches the configured secret.

    An empty configured token means no valid token exists, so every request is
    rejected — a cron job must be explicitly enabled by configuring a non-empty
    ``REBALANCE_CRON_TOKEN`` (the shared cron secret).
    """
    expected = settings.REBALANCE_CRON_TOKEN
    if (
        not expected
        or not x_cron_token
        or not hmac.compare_digest(x_cron_token, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing cron token",
        )
