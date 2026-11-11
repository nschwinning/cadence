"""Broker-account overview, Cadence reconciliation, and orphan flattening.

Cadence's ledgers are the source of truth for what each AI portfolio and strategy bot
owns; the broker account they all share is never consulted for that. This module puts
the two side by side:

- the **committed-cash check** sums the cash Cadence believes is spoken for and compares
  it with the account's real cash;
- the **positions comparison** matches the broker's holdings against every Cadence
  ledger per symbol and classifies each symbol (matched / orphan / shortfall / short);
- **flattening** sells the orphan excess — the shares no Cadence record claims — after
  recomputing it from live data, never from a client-supplied quantity.

Nothing here writes to the database: reads only, plus broker sells for orphans.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.bot_orchestrator.constants import OrchestratorStatus
from cadence.bot_orchestrator.models import BotOrchestrator
from cadence.broker.base import Broker, BrokerError
from cadence.broker.models import AssetClass, Order, Position
from cadence.paper_trading.constants import SessionStatus
from cadence.paper_trading.models import PaperTradingSession, SessionPosition
from cadence.strategy_bots.constants import BotSessionStatus
from cadence.strategy_bots.models import BotPosition, BotSession
from cadence.strategy_bots.service import bot_display_name

_logger = logging.getLogger(__name__)

# Quantities are floats (crypto and fractional equities); differences below this are
# treated as equal.
QUANTITY_EPSILON = 1e-6
# Alpaca accepts at most 9 decimal places on an order quantity.
_ORDER_QTY_DECIMALS = 9

PositionStatus = Literal["matched", "orphan", "shortfall", "short"]
ContributorKind = Literal["portfolio", "bot", "orchestrator", "returning_bot"]
FlattenResult = Literal["sold", "skipped", "failed"]


def symbol_key(symbol: str) -> str:
    """Spelling-independent symbol key: ``BRK.B``/``BRK-B`` → ``BRKB``, ``BTC/USD`` → ``BTCUSD``."""
    return "".join(ch for ch in symbol.upper() if ch not in "-/. ")


# Result shapes --------------------------------------------------------------
@dataclass(frozen=True)
class AccountFigures:
    cash: float
    buying_power: float
    portfolio_value: float
    currency: str


@dataclass(frozen=True)
class CashContributor:
    kind: ContributorKind
    id: str
    label: str
    amount: float


@dataclass(frozen=True)
class CashCheck:
    contributors: list[CashContributor]
    committed_total: float
    account_cash: float
    difference: float
    shortfall: bool


@dataclass(frozen=True)
class OpenOrder:
    order_id: str | None
    symbol: str
    side: str
    quantity: float
    order_type: str
    status: str
    submitted_at: datetime | None


@dataclass(frozen=True)
class PositionRow:
    symbol: str
    asset_class: str
    broker_quantity: float
    cadence_quantity: float
    orphan_quantity: float
    market_value: float | None
    status: PositionStatus
    pending_order: bool
    flattenable: bool


@dataclass(frozen=True)
class AccountOverview:
    broker_available: bool
    reason: str | None = None
    account: AccountFigures | None = None
    cash_check: CashCheck | None = None
    open_orders: list[OpenOrder] = field(default_factory=list)
    positions: list[PositionRow] = field(default_factory=list)


@dataclass(frozen=True)
class FlattenOutcome:
    symbol: str
    result: FlattenResult
    quantity: float | None = None
    order_id: str | None = None
    reason: str | None = None


# Cadence's books -------------------------------------------------------------
def _cadence_quantities(db: Session) -> dict[str, tuple[str, float]]:
    """Σ quantity per symbol key over every AI ledger and every bot (any status).

    Inactive owners count too: a stopped bot not yet flattened still owns its shares,
    so nothing any Cadence record claims is ever called an orphan. Values are
    ``(display ticker, quantity)``.
    """
    totals: dict[str, tuple[str, float]] = {}
    rows: Iterable[tuple[str, float]] = [
        *db.execute(select(SessionPosition.ticker, SessionPosition.quantity)).tuples(),
        *db.execute(select(BotPosition.ticker, BotPosition.quantity)).tuples(),
    ]
    for ticker, quantity in rows:
        key = symbol_key(ticker)
        display, held = totals.get(key, (ticker, 0.0))
        totals[key] = (display, held + quantity)
    return totals


def committed_cash(db: Session, account_cash: float) -> CashCheck:
    """Cash Cadence considers spoken for, itemised, against the account's cash."""
    contributors: list[CashContributor] = []

    sessions = db.execute(
        select(PaperTradingSession)
        .where(PaperTradingSession.status != SessionStatus.STOPPED.value)
        .where(PaperTradingSession.archived_at.is_(None))
        .order_by(PaperTradingSession.created_at)
    ).scalars()
    for row in sessions:
        cost = sum(p.quantity * p.avg_cost for p in row.positions)
        contributors.append(
            CashContributor(
                kind="portfolio",
                id=str(row.id),
                label=row.portfolio_name or row.strategy_key,
                amount=row.allocated_capital + row.total_pnl - row.total_fees - cost,
            )
        )

    bots = db.execute(select(BotSession).order_by(BotSession.created_at)).scalars()
    for bot in bots:
        if bot.status == BotSessionStatus.ACTIVE.value:
            kind: ContributorKind = "bot"
        elif bot.orchestrator_id is not None and bot.capital_returned_at is None:
            # Stopped orchestrator bot whose cash has not flowed back to the pool yet.
            kind = "returning_bot"
        else:
            continue
        contributors.append(
            CashContributor(kind=kind, id=str(bot.id), label=bot_display_name(bot), amount=bot.cash)
        )

    orchestrators = db.execute(
        select(BotOrchestrator)
        .where(BotOrchestrator.status == OrchestratorStatus.ACTIVE.value)
        .order_by(BotOrchestrator.created_at)
    ).scalars()
    for orchestrator in orchestrators:
        contributors.append(
            CashContributor(
                kind="orchestrator",
                id=str(orchestrator.id),
                label=orchestrator.label,
                amount=orchestrator.free_capital,
            )
        )

    total = sum(c.amount for c in contributors)
    difference = account_cash - total
    return CashCheck(
        contributors=contributors,
        committed_total=total,
        account_cash=account_cash,
        difference=difference,
        shortfall=difference < -QUANTITY_EPSILON,
    )


# Positions comparison --------------------------------------------------------
def _classify(broker_qty: float, cadence_qty: float) -> PositionStatus:
    if broker_qty < -QUANTITY_EPSILON:
        return "short"
    if broker_qty - cadence_qty > QUANTITY_EPSILON:
        return "orphan"
    if cadence_qty - broker_qty > QUANTITY_EPSILON:
        return "shortfall"
    return "matched"


def compare_positions(
    broker_positions: list[Position],
    cadence: dict[str, tuple[str, float]],
    open_orders: list[Order],
) -> list[PositionRow]:
    """One row per symbol held by the broker or tracked by Cadence, sorted by symbol."""
    pending = {symbol_key(o.symbol) for o in open_orders}
    held = {symbol_key(p.symbol): p for p in broker_positions}

    rows: list[PositionRow] = []
    for key in sorted(held.keys() | cadence.keys()):
        position = held.get(key)
        display, cadence_qty = cadence.get(key, ("", 0.0))
        broker_qty = position.quantity if position is not None else 0.0
        status = _classify(broker_qty, cadence_qty)
        orphan_qty = broker_qty - cadence_qty if status == "orphan" else 0.0
        has_pending = key in pending
        asset_class = (
            position.asset_class
            if position is not None and position.asset_class is not None
            else AssetClass.EQUITY
        )
        rows.append(
            PositionRow(
                symbol=position.symbol if position is not None else display,
                asset_class=asset_class.value,
                broker_quantity=broker_qty,
                cadence_quantity=cadence_qty,
                orphan_quantity=orphan_qty,
                market_value=position.market_value if position is not None else None,
                status=status,
                pending_order=has_pending,
                flattenable=status == "orphan" and not has_pending,
            )
        )
    return rows


def _open_order(order: Order) -> OpenOrder:
    return OpenOrder(
        order_id=order.order_id,
        symbol=order.symbol,
        side=order.side.value,
        quantity=order.quantity,
        order_type=order.order_type.value,
        status=order.status.value,
        submitted_at=order.submitted_at,
    )


# Overview --------------------------------------------------------------------
def account_overview(db: Session, broker: Broker) -> AccountOverview:
    """Live account figures, cash check, open orders and positions comparison.

    A broker failure yields ``broker_available=False`` with a non-secret reason and no
    figures, rather than an error or stale data.
    """
    try:
        info = broker.get_account_info()
        positions = broker.get_positions()
        orders = broker.get_open_orders()
    except BrokerError as exc:
        _logger.warning("admin account overview: broker unavailable", exc_info=True)
        return AccountOverview(broker_available=False, reason=str(exc) or "Broker error")

    return AccountOverview(
        broker_available=True,
        account=AccountFigures(
            cash=info.cash_balance,
            buying_power=info.buying_power,
            portfolio_value=info.portfolio_value,
            currency=info.currency,
        ),
        cash_check=committed_cash(db, info.cash_balance),
        open_orders=[_open_order(o) for o in orders],
        positions=compare_positions(positions, _cadence_quantities(db), orders),
    )


# Flattening ------------------------------------------------------------------
def flatten_orphans(
    db: Session, broker: Broker, *, symbol: str | None = None
) -> list[FlattenOutcome]:
    """Sell the recomputed orphan excess for ``symbol`` (or every orphan when ``None``).

    The comparison is rebuilt from live broker data and current Cadence records, so
    only the excess no Cadence record claims is ever sold. Symbols that are no longer
    orphans, have an open order, or are equities while the market is closed are
    skipped; a broker rejection is reported for that symbol and the rest still run.
    Nothing is written to any Cadence ledger. Raises :class:`BrokerError` when the
    broker cannot be read at all.
    """
    positions = broker.get_positions()
    orders = broker.get_open_orders()
    rows = compare_positions(positions, _cadence_quantities(db), orders)
    by_key = {symbol_key(p.symbol): p for p in positions}

    if symbol is None:
        targets = [r for r in rows if r.status == "orphan"]
    else:
        wanted = symbol_key(symbol)
        targets = [r for r in rows if symbol_key(r.symbol) == wanted]
        if not targets:
            return [FlattenOutcome(symbol=symbol, result="skipped", reason="not_found")]

    market_open: bool | None = None
    outcomes: list[FlattenOutcome] = []
    for row in targets:
        if row.status != "orphan":
            outcomes.append(_skipped(row.symbol, "not_orphan"))
            continue
        if row.pending_order:
            outcomes.append(_skipped(row.symbol, "pending_order"))
            continue
        asset_class = AssetClass(row.asset_class)
        if asset_class == AssetClass.EQUITY:
            if market_open is None:
                market_open = broker.is_market_open()
            if not market_open:
                outcomes.append(_skipped(row.symbol, "market_closed"))
                continue
        quantity = round(row.orphan_quantity, _ORDER_QTY_DECIMALS)
        broker_symbol = by_key[symbol_key(row.symbol)].symbol
        try:
            order = broker.sell(broker_symbol, quantity, asset_class=asset_class)
        except BrokerError as exc:
            _logger.warning(
                "admin flatten: sell of %s %s rejected",
                quantity,
                broker_symbol,
                exc_info=True,
            )
            outcomes.append(
                FlattenOutcome(
                    symbol=row.symbol, result="failed", quantity=quantity, reason=str(exc)
                )
            )
            continue
        _logger.info(
            "admin flatten: sold orphan %s %s (order %s)",
            quantity,
            broker_symbol,
            order.order_id,
        )
        outcomes.append(
            FlattenOutcome(
                symbol=row.symbol, result="sold", quantity=quantity, order_id=order.order_id
            )
        )
    return outcomes


def _skipped(symbol: str, reason: str) -> FlattenOutcome:
    _logger.info("admin flatten: skipped %s (%s)", symbol, reason)
    return FlattenOutcome(symbol=symbol, result="skipped", reason=reason)
