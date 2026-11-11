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

from cadence.assets.category import AssetCategory
from cadence.assets.models import Asset
from cadence.bot_orchestrator.constants import OrchestratorStatus
from cadence.bot_orchestrator.models import BotOrchestrator
from cadence.broker.base import Broker, BrokerError
from cadence.broker.models import AssetClass, Order, Position
from cadence.broker.symbols import symbol_key
from cadence.orders import journal
from cadence.orders.gateway import OrderGateway
from cadence.orders.models import OrderOwnerKind
from cadence.orders.reconcile import ReconcileResult, reconcile_orders
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
FlattenResult = Literal["sold", "bought", "skipped", "failed"]


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
    #: Free cash: the reported cash minus short-sale proceeds.
    account_cash: float
    difference: float
    shortfall: bool
    #: Cash as the broker reports it (inflated by any short-sale proceeds).
    reported_cash: float = 0.0
    #: Proceeds of short sales held in the reported cash (absolute short market value).
    short_proceeds: float = 0.0


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
    #: A shortfall or short with no open order: buying ``restore_quantity`` makes the
    #: account hold exactly what Cadence tracks.
    restorable: bool = False
    restore_quantity: float = 0.0


@dataclass(frozen=True)
class UnresolvedOrder:
    client_order_id: str
    owner_kind: str
    owner_label: str
    ticker: str
    side: str
    quantity: float
    state: str
    broker_status: str | None
    error: str | None
    created_at: datetime


@dataclass(frozen=True)
class AccountOverview:
    broker_available: bool
    reason: str | None = None
    account: AccountFigures | None = None
    cash_check: CashCheck | None = None
    open_orders: list[OpenOrder] = field(default_factory=list)
    positions: list[PositionRow] = field(default_factory=list)
    unresolved_orders: list[UnresolvedOrder] = field(default_factory=list)


@dataclass(frozen=True)
class FlattenOutcome:
    symbol: str
    result: FlattenResult
    quantity: float | None = None
    order_id: str | None = None
    reason: str | None = None


# Cadence's books -------------------------------------------------------------
def _cadence_quantities(db: Session) -> dict[str, tuple[str, float, AssetClass]]:
    """Σ quantity per symbol key over every AI ledger and every bot (any status).

    Inactive owners count too: a stopped bot not yet flattened still owns its shares,
    so nothing any Cadence record claims is ever called an orphan. Values are
    ``(display ticker, quantity, asset class)`` — the class from the asset universe
    (crypto iff its category is crypto), so a symbol the account no longer holds can
    still be bought back in the right class.
    """
    crypto = set(
        db.execute(
            select(Asset.ticker).where(Asset.category == AssetCategory.CRYPTO.value)
        ).scalars()
    )
    totals: dict[str, tuple[str, float, AssetClass]] = {}
    rows: Iterable[tuple[str, float]] = [
        *db.execute(select(SessionPosition.ticker, SessionPosition.quantity)).tuples(),
        *db.execute(select(BotPosition.ticker, BotPosition.quantity)).tuples(),
    ]
    for ticker, quantity in rows:
        key = symbol_key(ticker)
        display, held, cls = totals.get(
            key,
            (ticker, 0.0, AssetClass.CRYPTO if ticker in crypto else AssetClass.EQUITY),
        )
        totals[key] = (display, held + quantity, cls)
    return totals


def committed_cash(db: Session, account_cash: float, *, short_proceeds: float = 0.0) -> CashCheck:
    """Cash Cadence considers spoken for, itemised, against the account's free cash.

    ``account_cash`` is the cash the broker reports; ``short_proceeds`` (the absolute
    market value of short positions) is subtracted from it, because the proceeds of a
    short sale sit in the reported cash but are owed back.
    """
    reported_cash = account_cash
    account_cash = reported_cash - short_proceeds
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
        reported_cash=reported_cash,
        short_proceeds=short_proceeds,
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
    cadence: dict[str, tuple[str, float, AssetClass]],
    open_orders: list[Order],
) -> list[PositionRow]:
    """One row per symbol held by the broker or tracked by Cadence, sorted by symbol."""
    pending = {symbol_key(o.symbol) for o in open_orders}
    held = {symbol_key(p.symbol): p for p in broker_positions}

    rows: list[PositionRow] = []
    for key in sorted(held.keys() | cadence.keys()):
        position = held.get(key)
        display, cadence_qty, cadence_class = cadence.get(key, ("", 0.0, AssetClass.EQUITY))
        broker_qty = position.quantity if position is not None else 0.0
        status = _classify(broker_qty, cadence_qty)
        orphan_qty = broker_qty - cadence_qty if status == "orphan" else 0.0
        restore_qty = cadence_qty - broker_qty if status in ("shortfall", "short") else 0.0
        has_pending = key in pending
        asset_class = (
            position.asset_class
            if position is not None and position.asset_class is not None
            else cadence_class
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
                restorable=restore_qty > QUANTITY_EPSILON and not has_pending,
                restore_quantity=restore_qty,
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

    short_proceeds = sum(
        abs(p.market_value or p.quantity * (p.current_price or p.avg_cost))
        for p in positions
        if p.quantity < -QUANTITY_EPSILON
    )
    return AccountOverview(
        broker_available=True,
        account=AccountFigures(
            cash=info.cash_balance,
            buying_power=info.buying_power,
            portfolio_value=info.portfolio_value,
            currency=info.currency,
        ),
        cash_check=committed_cash(db, info.cash_balance, short_proceeds=short_proceeds),
        open_orders=[_open_order(o) for o in orders],
        positions=compare_positions(positions, _cadence_quantities(db), orders),
        unresolved_orders=unresolved_orders(db),
    )


def unresolved_orders(db: Session) -> list[UnresolvedOrder]:
    """Journaled orders not yet booked or closed out, with a readable owner name."""
    rows = journal.list_unresolved(db)
    labels: dict[object, str] = {}
    for row in rows:
        if row.owner_id is None or row.owner_id in labels:
            continue
        if row.owner_kind == OrderOwnerKind.BOT.value:
            bot = db.get(BotSession, row.owner_id)
            labels[row.owner_id] = bot_display_name(bot) if bot else str(row.owner_id)
        elif row.owner_kind == OrderOwnerKind.AI_SESSION.value:
            ai = db.get(PaperTradingSession, row.owner_id)
            labels[row.owner_id] = (
                (ai.portfolio_name or ai.strategy_key) if ai else str(row.owner_id)
            )
    return [
        UnresolvedOrder(
            client_order_id=row.client_order_id,
            owner_kind=row.owner_kind,
            owner_label=labels.get(row.owner_id, "Admin"),
            ticker=row.ticker,
            side=row.side,
            quantity=row.quantity,
            state=row.state,
            broker_status=row.broker_status,
            error=row.error,
            created_at=row.created_at,
        )
        for row in rows
    ]


def reconcile_now(db: Session, broker: Broker) -> ReconcileResult:
    """Run order reconciliation for every owner (the Admin "Reconcile now" action)."""
    return reconcile_orders(db, broker)


# Flattening and restoring ------------------------------------------------------
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
    return _adjust(db, broker, symbol=symbol, restore=False)


def restore_positions(
    db: Session, broker: Broker, *, symbol: str | None = None
) -> list[FlattenOutcome]:
    """Buy back shortfalls and shorts so the account holds exactly what Cadence tracks.

    Mirrors :func:`flatten_orphans`: recomputed at execution, never a caller quantity;
    skips symbols no longer short of Cadence's quantity, with an open order, or equities
    while the market is closed; per-symbol rejections are reported, the rest still run.
    The purchases are journaled administrator orders and touch no Cadence ledger.
    """
    return _adjust(db, broker, symbol=symbol, restore=True)


def _adjust(
    db: Session, broker: Broker, *, symbol: str | None, restore: bool
) -> list[FlattenOutcome]:
    positions = broker.get_positions()
    orders = broker.get_open_orders()
    cadence = _cadence_quantities(db)
    rows = compare_positions(positions, cadence, orders)
    by_key = {symbol_key(p.symbol): p for p in positions}
    eligible_statuses = ("shortfall", "short") if restore else ("orphan",)

    if symbol is None:
        targets = [r for r in rows if r.status in eligible_statuses]
    else:
        wanted = symbol_key(symbol)
        targets = [r for r in rows if symbol_key(r.symbol) == wanted]
        if not targets:
            return [FlattenOutcome(symbol=symbol, result="skipped", reason="not_found")]

    gateway = OrderGateway(broker, owner_kind=OrderOwnerKind.ADMIN)
    market_open: bool | None = None
    outcomes: list[FlattenOutcome] = []
    for row in targets:
        if row.status not in eligible_statuses:
            outcomes.append(_skipped(row.symbol, "not_short" if restore else "not_orphan"))
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
        key = symbol_key(row.symbol)
        held = by_key.get(key)
        broker_symbol = held.symbol if held is not None else row.symbol
        quantity = round(
            row.restore_quantity if restore else row.orphan_quantity, _ORDER_QTY_DECIMALS
        )
        purpose = "admin_restore" if restore else "admin_flatten"
        place = gateway.buy if restore else gateway.sell
        try:
            order = place(
                cadence[key][0] if key in cadence else broker_symbol,
                quantity,
                purpose=purpose,
                asset_class=asset_class,
                broker_symbol=broker_symbol,
            )
        except BrokerError as exc:
            _logger.warning(
                "admin %s: %s %s rejected", purpose, quantity, broker_symbol, exc_info=True
            )
            outcomes.append(
                FlattenOutcome(
                    symbol=row.symbol, result="failed", quantity=quantity, reason=str(exc)
                )
            )
            continue
        _logger.info("admin %s: %s %s (order %s)", purpose, quantity, broker_symbol, order.order_id)
        outcomes.append(
            FlattenOutcome(
                symbol=row.symbol,
                result="bought" if restore else "sold",
                quantity=quantity,
                order_id=order.order_id,
            )
        )
    return outcomes


def _skipped(symbol: str, reason: str) -> FlattenOutcome:
    _logger.info("admin: skipped %s (%s)", symbol, reason)
    return FlattenOutcome(symbol=symbol, result="skipped", reason=reason)
