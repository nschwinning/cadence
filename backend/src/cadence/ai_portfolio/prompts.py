"""Rebalance-prompt lookups for the AI-portfolio service.

Resolve the active (latest) prompt of a kind, or a specific pinned version — used
by the build flow to freeze a version onto a session and by the rebalance flow to
read that frozen version back. Append-only, versioned per :class:`PromptKind`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.ai_portfolio.constants import PromptKind
from cadence.ai_portfolio.errors import RebalancePromptNotFoundError
from cadence.ai_portfolio.models import RebalancePrompt


def get_active_rebalance_prompt(
    session: Session, kind: PromptKind = PromptKind.REBALANCE
) -> RebalancePrompt:
    """Return the active rebalance prompt of ``kind``: the row with the highest
    ``version`` within that kind.

    The prompt is stored append-only and versioned per kind (see
    :class:`RebalancePrompt`); "active" is simply the latest version for the kind.
    Migration seeds version 1 of each kind, so a row normally always exists. The
    ``kind`` filter is essential: version numbers overlap across kinds (both the
    ``rebalance`` and ``crypto_rebalance`` families start at v1).

    Raises:
        RebalancePromptNotFoundError: if no prompt version of ``kind`` exists.
    """
    stmt = (
        select(RebalancePrompt)
        .where(RebalancePrompt.kind == kind.value)
        .order_by(RebalancePrompt.version.desc())
        .limit(1)
    )
    prompt = session.execute(stmt).scalars().first()
    if prompt is None:
        raise RebalancePromptNotFoundError(
            f"no {kind.value} prompt is configured; seed version 1 before rebalancing"
        )
    return prompt


def get_rebalance_prompt_by_version(
    session: Session, version: int, kind: PromptKind = PromptKind.REBALANCE
) -> RebalancePrompt:
    """Return the rebalance prompt of ``kind`` pinned at ``version``.

    Used to resolve a session's frozen prompt version so every rebalance for that
    session uses the same prompt, regardless of later prompt edits. The ``kind``
    filter is required because versions are unique only per kind.

    Raises:
        RebalancePromptNotFoundError: if no prompt with that (kind, version) exists.
    """
    stmt = select(RebalancePrompt).where(
        RebalancePrompt.kind == kind.value,
        RebalancePrompt.version == version,
    )
    prompt = session.execute(stmt).scalars().first()
    if prompt is None:
        raise RebalancePromptNotFoundError(
            f"{kind.value} prompt version {version} not found"
        )
    return prompt
