"""restate historical fees under the asset-class-aware model

Revision ID: b1c2d3e4f5a6
Revises: f0a1b2c3d4e5
Create Date: 2026-10-09 10:00:00.000000

One-time DATA-ONLY restatement (no schema change). The retired flat $1/trade fee
is baked into every existing session's ``total_fees`` and into the historical
value snapshots (which subtract fees from portfolio value). This migration
restates that history as if the asset-class-aware model had always applied:

- Each session's ``total_fees`` is recomputed from its trade ledger — ``0`` for
  equity (non-crypto) trades and ``CRYPTO_FEE_PCT * quantity * executed_price``
  for crypto trades (the filled price when present, else the quoted price). A
  trade is crypto iff its ticker joins to an ``assets`` row whose category is
  crypto; an unresolvable ticker falls back to equity (no fee).
- Each recorded value snapshot's ``total_value``/``cash_value`` is lifted by the
  cumulative fee removed as of its date (``positions_value`` unchanged), and its
  ``daily_pnl``/``daily_pnl_pct`` are recomputed from the corrected series exactly
  as ``record_value_snapshot`` does.

The crypto percentage (0.0025) and the historical flat fee (1.0) are hardcoded
literals here rather than read from runtime ``settings``/ORM models, so a later
configuration or code change cannot retro-alter what this migration did. The
``downgrade`` inverts the same transform (flat fee restored), so the round-trip
returns the original recorded values.
"""
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: str | Sequence[str] | None = 'f0a1b2c3d4e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen literals: the crypto taker fee fraction adopted by this change and the
# retired flat per-trade fee the history was recorded under. Hardcoded on purpose
# (see module docstring) — do NOT import ``settings``.
CRYPTO_FEE_PCT = 0.0025
HISTORICAL_FLAT_FEE = 1.0
CRYPTO_CATEGORY = "crypto"


def _crypto_fee(trade: dict[str, Any]) -> float:
    """Asset-class-aware fee for a trade: crypto pays pct*notional, equity free."""
    if not trade["is_crypto"]:
        return 0.0
    price = trade["filled_price"] if trade["filled_price"] is not None else trade["price"]
    return CRYPTO_FEE_PCT * trade["quantity"] * price


def _flat_fee(trade: dict[str, Any]) -> float:
    """The retired flat per-trade fee (charged on every recorded fill)."""
    return HISTORICAL_FLAT_FEE


def compute_restatement(
    allocated_capital: float,
    trades: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    forward: bool,
) -> tuple[float, list[dict[str, Any]]]:
    """Pure, deterministic fee restatement for one session.

    ``trades`` carry ``quantity``/``price``/``filled_price``/``exec_date`` (the UTC
    execution date) and an ``is_crypto`` flag. ``snapshots`` are ordered oldest
    first with ``id``/``snapshot_date``/``total_value``/``cash_value``. ``events``
    are the session's capital events (``amount``/``effective_date``).

    ``forward`` restates the flat-fee history onto the asset-class-aware model;
    ``forward=False`` inverts it. Returns the session's new ``total_fees`` and the
    list of snapshot updates. This is a pure function of its inputs — re-deriving
    from the same ledger and original snapshots yields identical results.
    """
    fee_from, fee_to = (_flat_fee, _crypto_fee) if forward else (_crypto_fee, _flat_fee)

    total_fees_to = sum(fee_to(t) for t in trades)

    # Fee removed per execution date: correction(t) = old_fee − new_fee. Lifting a
    # snapshot dated D by the cumulative correction of all trades on/before D shifts
    # its total_value by exactly the change in cumulative fees as of that day.
    correction_by_date: dict[date, float] = {}
    for t in trades:
        correction_by_date[t["exec_date"]] = (
            correction_by_date.get(t["exec_date"], 0.0) + fee_from(t) - fee_to(t)
        )
    dates_sorted = sorted(correction_by_date)
    total_contributed = sum(e["amount"] for e in events)

    updates: list[dict[str, Any]] = []
    prev_total: float | None = None
    prev_date: date | None = None
    for snap in snapshots:
        day = snap["snapshot_date"]
        cum_correction = sum(
            correction_by_date[d] for d in dates_sorted if d <= day
        )
        new_total = snap["total_value"] + cum_correction
        new_cash = snap["cash_value"] + cum_correction

        # Recompute day-over-day P&L against the corrected prior baseline, matching
        # record_value_snapshot: baseline is the prior snapshot's (corrected) value,
        # or inception capital for the first; contributions in the window are netted
        # out so an added deposit is never read as a gain.
        if prev_total is not None:
            baseline = prev_total
            contributed = sum(
                e["amount"]
                for e in events
                if prev_date < e["effective_date"] <= day  # type: ignore[operator]
            )
        else:
            baseline = allocated_capital - total_contributed
            contributed = sum(
                e["amount"] for e in events if e["effective_date"] <= day
            )
        daily_pnl = new_total - contributed - baseline
        daily_pnl_pct = daily_pnl / baseline if baseline > 0 else 0.0

        updates.append(
            {
                "id": snap["id"],
                "total_value": new_total,
                "cash_value": new_cash,
                "daily_pnl": daily_pnl,
                "daily_pnl_pct": daily_pnl_pct,
            }
        )
        prev_total = new_total
        prev_date = day

    return total_fees_to, updates


def _restate(conn: sa.Connection, *, forward: bool) -> None:
    """Apply :func:`compute_restatement` to every session over ``conn``."""
    sessions = conn.execute(
        sa.text("SELECT id, allocated_capital FROM paper_trading_sessions")
    ).mappings().all()

    for s in sessions:
        sid = s["id"]
        trade_rows = conn.execute(
            sa.text(
                """
                SELECT
                    t.quantity AS quantity,
                    t.price AS price,
                    t.filled_price AS filled_price,
                    (t.executed_at AT TIME ZONE 'UTC')::date AS exec_date,
                    (a.category = :crypto) AS is_crypto
                FROM paper_trades t
                LEFT JOIN assets a ON a.ticker = t.ticker
                WHERE t.session_id = :sid
                """
            ),
            {"sid": sid, "crypto": CRYPTO_CATEGORY},
        ).mappings().all()
        trades = [
            {
                "quantity": r["quantity"],
                "price": r["price"],
                "filled_price": r["filled_price"],
                "exec_date": r["exec_date"],
                "is_crypto": bool(r["is_crypto"]),
            }
            for r in trade_rows
        ]

        snapshot_rows = conn.execute(
            sa.text(
                """
                SELECT id, snapshot_date, total_value, cash_value
                FROM session_value_snapshots
                WHERE session_id = :sid
                ORDER BY snapshot_date ASC
                """
            ),
            {"sid": sid},
        ).mappings().all()
        snapshots = [dict(r) for r in snapshot_rows]

        event_rows = conn.execute(
            sa.text(
                """
                SELECT amount, effective_date
                FROM session_capital_events
                WHERE session_id = :sid
                """
            ),
            {"sid": sid},
        ).mappings().all()
        events = [dict(r) for r in event_rows]

        total_fees_to, updates = compute_restatement(
            s["allocated_capital"], trades, snapshots, events, forward=forward
        )

        conn.execute(
            sa.text(
                "UPDATE paper_trading_sessions SET total_fees = :f WHERE id = :sid"
            ),
            {"f": total_fees_to, "sid": sid},
        )
        for u in updates:
            conn.execute(
                sa.text(
                    """
                    UPDATE session_value_snapshots
                    SET total_value = :tv,
                        cash_value = :cv,
                        daily_pnl = :dp,
                        daily_pnl_pct = :dpp
                    WHERE id = :id
                    """
                ),
                {
                    "tv": u["total_value"],
                    "cv": u["cash_value"],
                    "dp": u["daily_pnl"],
                    "dpp": u["daily_pnl_pct"],
                    "id": u["id"],
                },
            )


def upgrade() -> None:
    """Restate historical fees onto the asset-class-aware model (data only)."""
    _restate(op.get_bind(), forward=True)


def downgrade() -> None:
    """Restore the retired flat per-trade fee (inverse restatement, data only)."""
    _restate(op.get_bind(), forward=False)
