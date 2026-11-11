"""Tests for the broker-account admin: reconciliation, cash check and orphan flattening."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cadence.admin import service
from cadence.api.app import app
from cadence.assets.models import Asset
from cadence.bot_orchestrator import service as orchestrator_service
from cadence.broker import get_broker
from cadence.broker.base import Broker, ConnectionError, OrderError
from cadence.broker.models import AssetClass, Order, OrderType, Position, TimeInForce
from cadence.broker.stub import StubBroker
from cadence.paper_trading import service as paper_trading_service
from cadence.paper_trading.constants import Benchmark
from cadence.paper_trading.models import PaperTrade, PaperTradingSession, SessionPosition
from cadence.portfolios import service as portfolios_service
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.constants import BotOrigin
from cadence.strategy_bots.models import BotPosition, BotSession, BotTrade


# --- fixtures -----------------------------------------------------------------
def _asset(db: Session, ticker: str) -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db.add(asset)
    db.flush()
    return asset


def _ai_session(
    db: Session, *, name: str = "Growth", capital: float = 10_000.0
) -> PaperTradingSession:
    portfolio = portfolios_service.create_portfolio(db, name=name, stocks=["TECH"])
    return paper_trading_service.create_session(
        db,
        portfolio_id=portfolio.id,
        strategy_key="ai_managed",
        rebalance_prompt_version=1,
        crypto_rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
        allocated_capital=capital,
    )


def _ledger(db: Session, row: PaperTradingSession, ticker: str, qty: float, cost: float) -> None:
    db.add(SessionPosition(session_id=row.id, ticker=ticker, quantity=qty, avg_cost=cost))
    db.flush()
    db.refresh(row)


def _bot(db: Session, ticker: str, capital: float = 2_000.0, **kwargs: object) -> BotSession:
    return bot_service.create_bot_session(
        db,
        preset_key="donchian_turtle_algo25",
        tickers=[ticker],
        initial_capital=capital,
        benchmark="SP500",
        **kwargs,  # type: ignore[arg-type]
    )


def _bot_position(db: Session, bot: BotSession, asset: Asset, qty: float) -> None:
    db.add(
        BotPosition(
            bot_session_id=bot.id,
            asset_id=asset.id,
            ticker=asset.ticker,
            alpaca_symbol=asset.ticker.replace("-", "."),
            quantity=qty,
            avg_price=100.0,
        )
    )
    db.flush()
    db.refresh(bot)


def _broker(*holdings: tuple[str, float]) -> StubBroker:
    broker = StubBroker(initial_cash=1_000_000.0)
    for symbol, qty in holdings:
        broker.buy(symbol, qty)
    return broker


def _row(rows: list[service.PositionRow], symbol: str) -> service.PositionRow:
    return next(r for r in rows if service.symbol_key(r.symbol) == service.symbol_key(symbol))


class _ClosedMarketBroker(StubBroker):
    """Stub with a closed equity market and broker-reported asset classes."""

    def __init__(self, crypto: set[str]) -> None:
        super().__init__(initial_cash=1_000_000.0)
        self._crypto = crypto

    def is_market_open(self) -> bool:
        return False

    def get_positions(self) -> list[Position]:
        positions = super().get_positions()
        for p in positions:
            p.asset_class = AssetClass.CRYPTO if p.symbol in self._crypto else AssetClass.EQUITY
        return positions


class _RejectingBroker(StubBroker):
    """Stub whose sells of one symbol are rejected by the broker."""

    def __init__(self, reject: str) -> None:
        super().__init__(initial_cash=1_000_000.0)
        self._reject = reject

    def sell(  # type: ignore[override]
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        asset_class: AssetClass = AssetClass.EQUITY,
        client_order_id: str | None = None,
    ) -> Order:
        if symbol == self._reject:
            raise OrderError("Alpaca API error: insufficient qty available for order")
        return super().sell(
            symbol,
            quantity,
            order_type,
            limit_price,
            time_in_force,
            asset_class,
            client_order_id=client_order_id,
        )


class _DownBroker(StubBroker):
    def get_account_info(self):  # type: ignore[no-untyped-def]
        raise ConnectionError("Alpaca connection error: timed out")


# --- symbol key ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("a", "b"), [("BRK.B", "BRK-B"), ("BTCUSD", "BTC-USD"), ("BTC/USD", "btc-usd")]
)
def test_symbol_key_matches_spellings(a: str, b: str) -> None:
    assert service.symbol_key(a) == service.symbol_key(b)


# --- positions comparison -----------------------------------------------------
def test_symbol_owned_entirely_outside_cadence_is_an_orphan(db_session: Session) -> None:
    overview = service.account_overview(db_session, _broker(("XOM", 10)))

    row = _row(overview.positions, "XOM")
    assert (row.status, row.orphan_quantity, row.flattenable) == ("orphan", 10, True)


def test_shared_symbol_orphan_is_only_the_excess(db_session: Session) -> None:
    aapl = _asset(db_session, "AAPL")
    _ledger(db_session, _ai_session(db_session), "AAPL", 6, 100.0)
    _bot_position(db_session, _bot(db_session, "AAPL"), aapl, 4)

    overview = service.account_overview(db_session, _broker(("AAPL", 15)))

    row = _row(overview.positions, "AAPL")
    assert row.cadence_quantity == 10
    assert (row.status, row.orphan_quantity) == ("orphan", 5)


def test_stopped_bot_positions_still_count_as_cadence(db_session: Session) -> None:
    msft = _asset(db_session, "MSFT")
    bot = _bot(db_session, "MSFT")
    _bot_position(db_session, bot, msft, 4)
    bot_service.stop_bot_session(db_session, bot.id)

    overview = service.account_overview(db_session, _broker(("MSFT", 4)))

    assert _row(overview.positions, "MSFT").status == "matched"


def test_cadence_tracking_more_than_held_is_a_shortfall(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "NVDA", 10, 100.0)

    overview = service.account_overview(db_session, _broker(("NVDA", 6)))

    row = _row(overview.positions, "NVDA")
    assert (row.status, row.flattenable, row.orphan_quantity) == ("shortfall", False, 0)


def test_cadence_only_symbol_is_a_shortfall_row(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "AMD", 3, 100.0)

    overview = service.account_overview(db_session, _broker())

    row = _row(overview.positions, "AMD")
    assert (row.symbol, row.broker_quantity, row.status) == ("AMD", 0, "shortfall")


def test_class_share_spellings_reconcile(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "BRK-B", 2, 100.0)

    overview = service.account_overview(db_session, _broker(("BRK.B", 2)))

    assert [(r.symbol, r.status) for r in overview.positions] == [("BRK.B", "matched")]


def test_short_position_is_flagged_not_flattenable() -> None:
    rows = service.compare_positions([Position(symbol="TSLA", quantity=-3, avg_cost=1)], {}, [])

    assert (rows[0].status, rows[0].flattenable) == ("short", False)


def test_pending_order_blocks_flattening(db_session: Session) -> None:
    broker = _broker(("XOM", 10))
    broker.sell("XOM", 1, order_type=OrderType.LIMIT, limit_price=1_000_000.0)

    overview = service.account_overview(db_session, broker)

    row = _row(overview.positions, "XOM")
    assert (row.status, row.pending_order, row.flattenable) == ("orphan", True, False)
    assert [o.symbol for o in overview.open_orders] == ["XOM"]


# --- cash check ---------------------------------------------------------------
def test_cash_check_itemises_and_sums_contributors(db_session: Session) -> None:
    _asset(db_session, "AAPL")
    _asset(db_session, "MSFT")
    session_row = _ai_session(db_session, name="Growth", capital=10_000.0)
    _ledger(db_session, session_row, "AAPL", 10, 100.0)  # 1,000 invested → 9,000 cash
    manual = _bot(db_session, "AAPL", capital=2_000.0)
    orchestrator = orchestrator_service.create_orchestrator(
        db_session, label="First Orchestrator", capital=5_000.0
    )
    orchestrator.free_capital -= 1_500.0
    deployed = _bot(
        db_session,
        "MSFT",
        capital=1_500.0,
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )
    bot_service.stop_bot_session(db_session, deployed.id)  # stopped, cash not yet returned
    stopped_manual = _bot(db_session, "MSFT", capital=700.0)
    bot_service.stop_bot_session(db_session, stopped_manual.id)  # no longer committed

    check = service.committed_cash(db_session, account_cash=20_000.0)

    by_kind = {(c.kind, c.label): c.amount for c in check.contributors}
    assert by_kind == {
        ("portfolio", "Growth"): pytest.approx(9_000.0),
        ("bot", bot_service.bot_display_name(manual)): 2_000.0,
        ("returning_bot", bot_service.bot_display_name(deployed)): 1_500.0,
        ("orchestrator", "First Orchestrator"): 3_500.0,
    }
    assert check.committed_total == pytest.approx(16_000.0)
    assert check.difference == pytest.approx(4_000.0)
    assert check.shortfall is False


def test_cash_check_flags_a_shortfall(db_session: Session) -> None:
    _ai_session(db_session, capital=10_000.0)

    check = service.committed_cash(db_session, account_cash=8_000.0)

    assert check.difference == pytest.approx(-2_000.0)
    assert check.shortfall is True


def test_overview_writes_nothing(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "AAPL", 2, 100.0)
    before = db_session.execute(select(func.count()).select_from(SessionPosition)).scalar()

    service.account_overview(db_session, _broker(("AAPL", 5)))

    assert not db_session.dirty and not db_session.new
    after = db_session.execute(select(func.count()).select_from(SessionPosition)).scalar()
    assert before == after


def test_broker_unavailable_yields_no_figures(db_session: Session) -> None:
    overview = service.account_overview(db_session, _DownBroker())

    assert overview.broker_available is False
    assert "timed out" in (overview.reason or "")
    assert overview.account is None and overview.positions == [] and overview.open_orders == []


# --- flattening ---------------------------------------------------------------
def test_flatten_single_orphan_sells_only_the_excess(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "AAPL", 10, 100.0)
    broker = _broker(("AAPL", 15))

    outcomes = service.flatten_orphans(db_session, broker, symbol="AAPL")

    assert [(o.symbol, o.result, o.quantity) for o in outcomes] == [("AAPL", "sold", 5)]
    assert broker.get_position("AAPL").quantity == 10  # type: ignore[union-attr]


def test_flatten_uses_the_recomputed_quantity(db_session: Session) -> None:
    broker = _broker(("XOM", 10))
    before = service.account_overview(db_session, broker)
    assert _row(before.positions, "XOM").orphan_quantity == 10
    # Cadence starts tracking part of it after the page was loaded.
    _ledger(db_session, _ai_session(db_session), "XOM", 7, 100.0)

    outcomes = service.flatten_orphans(db_session, broker, symbol="XOM")

    assert [(o.result, o.quantity) for o in outcomes] == [("sold", 3)]


def test_flatten_skips_a_symbol_that_is_no_longer_orphaned(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "AAPL", 5, 100.0)

    outcomes = service.flatten_orphans(db_session, _broker(("AAPL", 5)), symbol="AAPL")

    assert [(o.result, o.reason) for o in outcomes] == [("skipped", "not_orphan")]


def test_flatten_unknown_symbol_is_skipped(db_session: Session) -> None:
    outcomes = service.flatten_orphans(db_session, _broker(), symbol="ZZZ")

    assert [(o.symbol, o.result, o.reason) for o in outcomes] == [("ZZZ", "skipped", "not_found")]


def test_flatten_skips_pending_orders(db_session: Session) -> None:
    broker = _broker(("XOM", 10))
    broker.sell("XOM", 1, order_type=OrderType.LIMIT, limit_price=1_000_000.0)

    outcomes = service.flatten_orphans(db_session, broker, symbol="XOM")

    assert [(o.result, o.reason) for o in outcomes] == [("skipped", "pending_order")]


def test_closed_market_skips_equities_but_sells_crypto(db_session: Session) -> None:
    broker = _ClosedMarketBroker(crypto={"BTC-USD"})
    broker.buy("XOM", 10)
    broker.buy("BTC-USD", 0.5)

    outcomes = service.flatten_orphans(db_session, broker)

    assert {(o.symbol, o.result, o.reason) for o in outcomes} == {
        ("BTC-USD", "sold", None),
        ("XOM", "skipped", "market_closed"),
    }


def test_flatten_all_continues_past_a_rejection(db_session: Session) -> None:
    broker = _RejectingBroker(reject="XOM")
    broker.buy("XOM", 10)
    broker.buy("CVX", 4)
    _ledger(db_session, _ai_session(db_session), "AAPL", 1, 100.0)
    broker.buy("AAPL", 1)  # matched: not targeted by flatten-all

    outcomes = service.flatten_orphans(db_session, broker)

    by_symbol = {o.symbol: o for o in outcomes}
    assert set(by_symbol) == {"CVX", "XOM"}
    assert by_symbol["CVX"].result == "sold"
    assert by_symbol["XOM"].result == "failed"
    assert "insufficient qty" in (by_symbol["XOM"].reason or "")


def test_flatten_leaves_cadence_books_untouched(db_session: Session) -> None:
    session_row = _ai_session(db_session, capital=10_000.0)
    _ledger(db_session, session_row, "AAPL", 2, 100.0)
    orchestrator = orchestrator_service.create_orchestrator(
        db_session, label="Pool", capital=5_000.0
    )

    def counts() -> tuple[int | None, ...]:
        return tuple(
            db_session.execute(select(func.count()).select_from(model)).scalar()
            for model in (SessionPosition, PaperTrade, BotPosition, BotTrade)
        )

    before = counts()
    service.flatten_orphans(db_session, _broker(("AAPL", 9), ("XOM", 3)))

    assert counts() == before
    db_session.refresh(session_row)
    db_session.refresh(orchestrator)
    assert (session_row.total_pnl, session_row.total_fees) == (0.0, 0.0)
    assert orchestrator.free_capital == 5_000.0


# --- HTTP ---------------------------------------------------------------------
def _use_broker(broker: Broker) -> None:
    app.dependency_overrides[get_broker] = lambda: broker


def test_account_endpoint_shape(client: TestClient, db_session: Session) -> None:
    _use_broker(_broker(("XOM", 10)))

    body = client.get("/api/v1/admin/account").json()

    assert body["broker_available"] is True
    assert body["account"]["cash"] > 0
    assert body["cash_check"]["shortfall"] is False
    assert body["positions"][0]["symbol"] == "XOM"
    assert body["positions"][0]["status"] == "orphan"
    assert body["open_orders"] == []


def test_account_endpoint_reports_unavailable_broker(client: TestClient) -> None:
    _use_broker(_DownBroker())

    response = client.get("/api/v1/admin/account")

    assert response.status_code == 200
    body = response.json()
    assert body["broker_available"] is False
    assert body["account"] is None


def test_flatten_endpoint_single_and_all(client: TestClient) -> None:
    broker = _broker(("XOM", 10), ("CVX", 2))
    _use_broker(broker)

    single = client.post("/api/v1/admin/flatten-orphans", json={"symbol": "XOM"}).json()
    rest = client.post("/api/v1/admin/flatten-orphans", json={}).json()

    assert [(o["symbol"], o["result"], o["quantity"]) for o in single["outcomes"]] == [
        ("XOM", "sold", 10)
    ]
    assert [(o["symbol"], o["result"]) for o in rest["outcomes"]] == [("CVX", "sold")]


def test_flatten_endpoint_rejects_a_client_quantity(client: TestClient) -> None:
    _use_broker(_broker(("XOM", 10)))

    response = client.post("/api/v1/admin/flatten-orphans", json={"symbol": "XOM", "quantity": 10})

    assert response.status_code == 422


def test_flatten_endpoint_503_when_broker_unreadable(client: TestClient) -> None:
    class _Unreadable(StubBroker):
        def get_positions(self) -> list[Position]:
            raise ConnectionError("Alpaca connection error: timed out")

    _use_broker(_Unreadable())

    response = client.post("/api/v1/admin/flatten-orphans", json={})

    assert response.status_code == 503


# --- restore -------------------------------------------------------------------
class _ShortBroker(StubBroker):
    """Stub reporting extra short positions (the stub itself cannot sell short)."""

    def __init__(self, shorts: dict[str, float], *, market_open: bool = True) -> None:
        super().__init__(initial_cash=1_000_000.0)
        self._shorts = shorts
        self._open = market_open
        self.bought: list[tuple[str, float]] = []

    def is_market_open(self) -> bool:
        return self._open

    def get_positions(self) -> list[Position]:
        positions = [p for p in super().get_positions() if p.symbol not in self._shorts]
        positions += [
            Position(symbol=s, quantity=q, avg_cost=100.0, market_value=q * 100.0)
            for s, q in self._shorts.items()
        ]
        return positions

    def buy(self, symbol, quantity, *args, **kwargs):  # type: ignore[no-untyped-def, override]
        self.bought.append((symbol, quantity))
        return super().buy(symbol, quantity, *args, **kwargs)


def test_short_position_is_restored_to_cadence_quantity(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "TSLA", 4, 100.0)
    broker = _ShortBroker({"TSLA": -6})

    row = _row(service.account_overview(db_session, broker).positions, "TSLA")
    assert (row.status, row.restorable, row.restore_quantity) == ("short", True, 10)

    outcomes = service.restore_positions(db_session, broker, symbol="TSLA")

    assert [(o.symbol, o.result, o.quantity) for o in outcomes] == [("TSLA", "bought", 10)]
    # Cover first, then Cadence's quantity: a single order may not flip short → long.
    assert broker.bought == [("TSLA", 6), ("TSLA", 4)]


def test_shortfall_is_restored(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "NVDA", 10, 100.0)
    broker = _broker(("NVDA", 6))

    outcomes = service.restore_positions(db_session, broker)

    assert [(o.symbol, o.result, o.quantity) for o in outcomes] == [("NVDA", "bought", 4)]
    assert broker.get_position("NVDA").quantity == 10  # type: ignore[union-attr]


def test_cadence_only_crypto_is_restored_as_crypto(db_session: Session) -> None:
    db_session.add(
        Asset(
            ticker="BTC-USD",
            name="Bitcoin",
            sector=None,
            category="crypto",
            currency="USD",
            is_eligible=True,
            criteria_results=[],
        )
    )
    _ledger(db_session, _ai_session(db_session), "BTC-USD", 0.5, 60_000.0)
    broker = _ShortBroker({}, market_open=False)

    [row] = service.account_overview(db_session, broker).positions
    assert (row.symbol, row.asset_class, row.restore_quantity) == ("BTC-USD", "crypto", 0.5)
    outcomes = service.restore_positions(db_session, broker)

    assert [(o.result, o.quantity) for o in outcomes] == [("bought", 0.5)]


def test_restore_skips_matched_orphan_pending_and_closed_market(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "AAPL", 5, 100.0)
    _ledger(db_session, _ai_session(db_session, name="Value"), "CVX", 5, 100.0)
    broker = _ShortBroker({"CVX": -1}, market_open=False)
    broker.buy("AAPL", 5)
    broker.buy("XOM", 3)

    assert [
        (o.result, o.reason) for o in service.restore_positions(db_session, broker, symbol="AAPL")
    ] == [("skipped", "not_short")]
    assert [
        (o.result, o.reason) for o in service.restore_positions(db_session, broker, symbol="XOM")
    ] == [("skipped", "not_short")]
    assert [
        (o.result, o.reason) for o in service.restore_positions(db_session, broker, symbol="CVX")
    ] == [("skipped", "market_closed")]

    pending = _broker(("XOM", 3))
    _ledger(db_session, _ai_session(db_session, name="Third"), "XOM", 5, 100.0)
    pending.buy("XOM", 1, order_type=OrderType.LIMIT, limit_price=0.01)
    assert [
        (o.result, o.reason) for o in service.restore_positions(db_session, pending, symbol="XOM")
    ] == [("skipped", "pending_order")]


def test_restore_leaves_cadence_books_untouched(db_session: Session) -> None:
    session_row = _ai_session(db_session, capital=10_000.0)
    _ledger(db_session, session_row, "NVDA", 10, 100.0)
    before = db_session.execute(select(func.count()).select_from(PaperTrade)).scalar()

    service.restore_positions(db_session, _broker(("NVDA", 6)))

    assert db_session.execute(select(func.count()).select_from(PaperTrade)).scalar() == before
    db_session.refresh(session_row)
    assert [p.quantity for p in session_row.positions] == [10]


# --- cash check vs shorts -----------------------------------------------------------
def test_cash_check_excludes_short_sale_proceeds(db_session: Session) -> None:
    broker = _ShortBroker({"TSLA": -2_010})  # 2,010 × $100 = $201,000 short

    overview = service.account_overview(db_session, broker)

    check = overview.cash_check
    assert check is not None
    assert check.reported_cash == pytest.approx(1_000_000.0)
    assert check.short_proceeds == pytest.approx(201_000.0)
    assert check.account_cash == pytest.approx(799_000.0)


# --- unresolved orders and reconcile -----------------------------------------------
def test_unresolved_orders_are_listed_and_reconciled(db_session: Session) -> None:
    from datetime import UTC, datetime, timedelta

    from cadence.orders.gateway import OrderGateway
    from cadence.orders.models import OrderOwnerKind
    from cadence.orders.reconcile import reconcile_orders

    session_row = _ai_session(db_session, name="Growth")
    broker = StubBroker()
    OrderGateway(broker, owner_kind=OrderOwnerKind.AI_SESSION, owner_id=session_row.id).buy(
        "MSFT", 2, purpose="ai_rebalance_buy"
    )

    [unresolved] = service.account_overview(db_session, broker).unresolved_orders
    assert (unresolved.owner_label, unresolved.ticker, unresolved.side) == ("Growth", "MSFT", "buy")

    result = reconcile_orders(db_session, broker, now=datetime.now(UTC) + timedelta(hours=1))
    assert result.booked == 1
    assert service.account_overview(db_session, broker).unresolved_orders == []


def test_admin_orders_are_journaled(db_session: Session) -> None:
    from cadence.orders.models import BrokerOrder

    service.flatten_orphans(db_session, _broker(("XOM", 3)), symbol="XOM")

    db_session.expire_all()
    [row] = db_session.execute(select(BrokerOrder)).scalars()
    assert (row.owner_kind, row.purpose, row.side, row.quantity) == (
        "admin",
        "admin_flatten",
        "sell",
        3,
    )
    assert row.booked_at is not None


def test_restore_and_reconcile_endpoints(client: TestClient, db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "NVDA", 10, 100.0)
    _use_broker(_broker(("NVDA", 6)))

    restore = client.post("/api/v1/admin/restore-positions", json={"symbol": None})
    reconcile = client.post("/api/v1/admin/reconcile-orders")
    rejected = client.post(
        "/api/v1/admin/restore-positions", json={"symbol": "NVDA", "quantity": 1}
    )

    assert restore.status_code == 200
    assert restore.json()["outcomes"][0]["result"] == "bought"
    assert reconcile.json() == {"booked": 0, "closed": 0, "remaining": 0}
    assert rejected.status_code == 422
    body = client.get("/api/v1/admin/account").json()
    assert body["unresolved_orders"] == []
    assert {"reported_cash", "short_proceeds"} <= body["cash_check"].keys()
    assert {"restorable", "restore_quantity"} <= body["positions"][0].keys()


# --- restoring shorts the way Alpaca allows ------------------------------------------
class _AlpacaShortBroker(StubBroker):
    """Tracks short positions and, like Alpaca, refuses a buy that would flip one long.

    ``fill_covers=False`` leaves cover orders working (as if not yet filled).
    """

    def __init__(self, shorts: dict[str, float], *, fill_covers: bool = True) -> None:
        super().__init__(initial_cash=1_000_000.0)
        self.shorts = dict(shorts)
        self._fill_covers = fill_covers
        self.reject_long: set[str] = set()
        self.bought: list[tuple[str, float]] = []

    def get_positions(self) -> list[Position]:
        open_shorts = {s for s, q in self.shorts.items() if q > 0}
        held = [p for p in super().get_positions() if p.symbol not in open_shorts]
        return held + [
            Position(symbol=s, quantity=-q, avg_cost=100.0, market_value=-q * 100.0)
            for s, q in self.shorts.items()
            if q > 0
        ]

    def buy(self, symbol, quantity, *args, **kwargs):  # type: ignore[no-untyped-def, override]
        from cadence.broker.base import OrderError
        from cadence.broker.models import OrderSide, OrderStatus

        short = self.shorts.get(symbol, 0.0)
        if short > 0:
            if quantity > short:
                raise OrderError(
                    "Alpaca API error: insufficient qty available for order "
                    f"(requested: {quantity:g}, available: {short:g})"
                )
            self.bought.append((symbol, quantity))
            order = Order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                order_id=self._next_order_id(),
                client_order_id=kwargs.get("client_order_id"),
                status=OrderStatus.FILLED if self._fill_covers else OrderStatus.SUBMITTED,
                filled_quantity=quantity if self._fill_covers else 0.0,
                filled_price=100.0 if self._fill_covers else None,
            )
            self._orders[order.order_id or ""] = order
            if self._fill_covers:
                self.shorts[symbol] = short - quantity
            return order
        if symbol in self.reject_long:
            raise OrderError("Alpaca API error: insufficient buying power")
        self.bought.append((symbol, quantity))
        return super().buy(symbol, quantity, *args, **kwargs)


def test_short_with_cadence_shares_is_covered_then_rebuilt(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "PSA", 1, 100.0)
    _ledger(db_session, _ai_session(db_session, name="Utilities"), "AWK", 8, 100.0)
    broker = _AlpacaShortBroker({"PSA": 75, "AWK": 608})

    outcomes = service.restore_positions(db_session, broker)

    assert {(o.symbol, o.result, o.quantity, o.reason) for o in outcomes} == {
        ("PSA", "bought", 76, None),
        ("AWK", "bought", 616, None),
    }
    assert broker.bought == [("AWK", 608), ("AWK", 8), ("PSA", 75), ("PSA", 1)]
    rows = {r.symbol: r.status for r in service.account_overview(db_session, broker).positions}
    assert rows == {"AWK": "matched", "PSA": "matched"}


def test_short_cadence_does_not_track_is_a_single_cover(db_session: Session) -> None:
    broker = _AlpacaShortBroker({"PSA": 75})

    [outcome] = service.restore_positions(db_session, broker)

    assert (outcome.result, outcome.quantity) == ("bought", 75)
    assert broker.bought == [("PSA", 75)]


def test_unfilled_cover_reports_the_remainder(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "PSA", 1, 100.0)
    broker = _AlpacaShortBroker({"PSA": 75}, fill_covers=False)

    [outcome] = service.restore_positions(db_session, broker)

    assert (outcome.result, outcome.quantity) == ("bought", 75)
    assert "run Restore again to buy the remaining 1" in (outcome.reason or "")
    assert broker.bought == [("PSA", 75)]


def test_rejected_rebuild_after_cover_is_reported(db_session: Session) -> None:
    _ledger(db_session, _ai_session(db_session), "AWK", 8, 100.0)
    broker = _AlpacaShortBroker({"AWK": 608})
    broker.reject_long = {"AWK"}

    [outcome] = service.restore_positions(db_session, broker)

    assert (outcome.result, outcome.quantity) == ("failed", 608)
    assert "covered 608; buying the remaining 8 failed" in (outcome.reason or "")
    assert "insufficient buying power" in (outcome.reason or "")


def test_rejected_cover_sends_nothing_else(db_session: Session) -> None:
    from cadence.broker.base import OrderError

    _ledger(db_session, _ai_session(db_session), "PSA", 1, 100.0)

    class _CoverRejected(_AlpacaShortBroker):
        def buy(self, symbol, quantity, *args, **kwargs):  # type: ignore[no-untyped-def, override]
            raise OrderError("Alpaca API error: insufficient buying power")

    broker = _CoverRejected({"PSA": 75})

    [outcome] = service.restore_positions(db_session, broker)

    assert (outcome.result, outcome.quantity) == ("failed", 75)
    assert "insufficient buying power" in (outcome.reason or "")
    assert broker.bought == []
