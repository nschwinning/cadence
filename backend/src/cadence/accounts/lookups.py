"""Owner lookups usable from domain code (no web-framework imports).

Callers use their own database session, so the lookup also sees rows they created in
the current, not-yet-committed transaction.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.accounts.models import LEGACY_OWNER_ID


def session_owner_id(db: Session, session_id: uuid.UUID) -> uuid.UUID:
    """The owner of a paper-trading session (its portfolio's owner; legacy if unknown)."""
    from cadence.paper_trading.models import PaperTradingSession
    from cadence.portfolios.models import Portfolio

    owner = db.execute(
        select(Portfolio.owner_user_id)
        .join(PaperTradingSession, PaperTradingSession.portfolio_id == Portfolio.id)
        .where(PaperTradingSession.id == session_id)
    ).scalar_one_or_none()
    return owner if owner is not None else LEGACY_OWNER_ID
