"""Read-only access to the LiteLLM proxy's spend log for per-session AI cost.

The LiteLLM proxy records authoritative, provider-reported per-request cost in
its own ``litellm`` database (a separate database on the same Postgres instance
as the app). This module sums the cost attributed to a paper-trading session —
the ``cadence_session_id`` that the rebalance flow stamps into each run's
spend-log metadata (see :mod:`cadence.agents.gateway`).

Everything here is **best-effort and opt-in**: when ``LITELLM_DATABASE_URL`` is
unset the cost is reported as ``None`` and the database is never touched, and any
connection/query error is swallowed to ``None`` so a session's other KPIs are
never blocked. This is the ONE place coupled to LiteLLM's schema — the
``LiteLLM_SpendLogs`` table and its nested ``spend_logs_metadata`` key.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from cadence.config import settings

logger = logging.getLogger(__name__)

# LiteLLM-owned spend-log table and the metadata key the gateway stamps the
# Cadence session id under. If a LiteLLM upgrade renames either, the query fails
# soft (cost → None) rather than breaking session detail.
_SPEND_TABLE = "LiteLLM_SpendLogs"
_SESSION_METADATA_KEY = "cadence_session_id"


def _normalize_url(url: str) -> str:
    """Pin the psycopg3 driver (the app's driver) for a bare ``postgresql://`` DSN."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache(maxsize=4)
def _spend_engine(url: str) -> Engine:
    """Build (once per URL) a small read-only engine to the LiteLLM spend DB."""
    return create_engine(
        _normalize_url(url),
        echo=False,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=1,
    )


def session_ai_cost_usd(session_id: str) -> float | None:
    """Return the cumulative USD AI cost attributed to ``session_id``.

    ``None`` when the cost source is unconfigured, has no spend for the session,
    or cannot be read — never raises.
    """
    url = settings.LITELLM_DATABASE_URL.strip()
    if not url:
        return None
    query = text(
        f'SELECT SUM(spend) FROM "{_SPEND_TABLE}" '
        f"WHERE metadata->'spend_logs_metadata'->>'{_SESSION_METADATA_KEY}' = :sid"
    )
    try:
        with _spend_engine(url).connect() as conn:
            total = conn.execute(query, {"sid": session_id}).scalar()
    except Exception:
        # Best-effort KPI: any connection/query failure degrades to no cost rather
        # than breaking the session's other KPIs.
        logger.warning("Failed to read AI cost for session %s", session_id, exc_info=True)
        return None
    return float(total) if total is not None else None
