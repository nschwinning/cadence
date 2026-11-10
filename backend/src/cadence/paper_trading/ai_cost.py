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
from collections.abc import Sequence
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from cadence.config import settings

logger = logging.getLogger(__name__)

# LiteLLM-owned spend-log table and the metadata key the gateway stamps the
# Cadence session id under. If a LiteLLM upgrade renames either, the query fails
# soft (cost → None) rather than breaking session detail.
_SPEND_TABLE = "LiteLLM_SpendLogs"
_SESSION_METADATA_KEY = "cadence_session_id"
# The per-run trace id every llm_trace() run carries (see cadence.agents.gateway).
_TRACE_METADATA_KEY = "cadence_trace_id"


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


def cost_source_configured() -> bool:
    """Whether the LiteLLM spend database is configured (costs can be read at all)."""
    return bool(settings.LITELLM_DATABASE_URL.strip())


def _costs_by_metadata_key(key: str, values: Sequence[str]) -> dict[str, float] | None:
    """Sum ``spend`` per value of a spend-log metadata ``key`` in one grouped query.

    The shared batched lookup behind :func:`session_ai_costs_usd` and
    :func:`trace_ai_costs_usd`. Degradation:

    - ``None`` when ``LITELLM_DATABASE_URL`` is unconfigured, or when the query
      fails for any reason (logged, never raised) — the caller treats this as
      "cost source unavailable".
    - ``{}`` for an empty ``values`` (the database is never touched).
    - Otherwise a ``{value: float(sum)}`` map. Values with no recorded spend are
      **absent** from the map (callers render them as ``0``, distinct from the
      unavailable ``None`` state).
    """
    if not values:
        return {}
    url = settings.LITELLM_DATABASE_URL.strip()
    if not url:
        return None
    query = text(
        f"SELECT metadata->'spend_logs_metadata'->>'{key}' AS sid, "
        f'SUM(spend) AS total FROM "{_SPEND_TABLE}" '
        f"WHERE metadata->'spend_logs_metadata'->>'{key}' = ANY(:sids) "
        "GROUP BY sid"
    )
    try:
        with _spend_engine(url).connect() as conn:
            rows = conn.execute(query, {"sids": list(values)}).all()
    except Exception:
        # Best-effort figures: any connection/query failure degrades to the
        # unavailable state rather than breaking the caller.
        logger.warning(
            "Failed to read AI costs for %d %s values", len(values), key, exc_info=True
        )
        return None
    return {
        sid: float(total) for sid, total in rows if sid is not None and total is not None
    }


def session_ai_costs_usd(session_ids: Sequence[str]) -> dict[str, float] | None:
    """Return a map of ``session_id -> cumulative USD AI cost`` in one query.

    Reads the same LiteLLM ``SpendLogs`` source as :func:`session_ai_cost_usd`,
    aggregating all requested sessions with a single grouped query (see
    :func:`_costs_by_metadata_key` for the degradation contract).
    """
    return _costs_by_metadata_key(_SESSION_METADATA_KEY, session_ids)


def trace_ai_costs_usd(trace_ids: Sequence[str]) -> dict[str, float] | None:
    """Return a map of ``trace_id -> USD AI cost`` in one query.

    Every agent run started under :func:`cadence.agents.llm_trace` is tagged with its
    trace id, so this attributes spend to individual runs (e.g. bot-orchestrator
    decision runs) without any extra metadata. Same degradation contract as
    :func:`session_ai_costs_usd`.
    """
    return _costs_by_metadata_key(_TRACE_METADATA_KEY, trace_ids)
