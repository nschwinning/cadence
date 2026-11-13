"""Shared pytest fixtures.

Tests run against a dedicated Postgres database (``TEST_DATABASE_URL``), never
the development/production ``DATABASE_URL``. The test database is created on
demand and its schema is built from the ORM models at session start. Each test
runs inside an outer transaction that is rolled back afterwards, so the test
database stays empty between tests.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

# Import every model module so ``Base.metadata`` is fully populated before we
# create the schema on the test database.
from tests.fakes import FakeFundamentalsProvider

from cadence import environment
from cadence.ai_portfolio import models as _ai_portfolio_models  # noqa: F401
from cadence.api.app import app
from cadence.api.routers.assets import get_fundamentals_provider
from cadence.assets import models as _assets_models  # noqa: F401
from cadence.assets.fundamentals import FundamentalsProvider
from cadence.bot_orchestrator import models as _bot_orchestrator_models  # noqa: F401
from cadence.broker import Broker, get_broker
from cadence.broker.stub import StubBroker
from cadence.config import settings
from cadence.database import Base, SessionLocal, get_db
from cadence.news_sentiment import news as news_module
from cadence.orders import journal as order_journal
from cadence.orders import models as _orders_models  # noqa: F401
from cadence.paper_trading import models as _paper_trading_models  # noqa: F401
from cadence.portfolios import models as _portfolios_models  # noqa: F401
from cadence.price_ml import models as _price_ml_models  # noqa: F401
from cadence.recommendations import models as _recommendations_models  # noqa: F401
from cadence.strategy_bots import models as _strategy_bots_models  # noqa: F401
from cadence.technical_indicators import models as _technical_indicator_models  # noqa: F401


def _ensure_database_exists(url: str) -> None:
    """Create the target database if it does not already exist.

    Connects to the server's ``postgres`` maintenance database with AUTOCOMMIT
    (``CREATE DATABASE`` cannot run inside a transaction) and creates the test
    database when missing.
    """
    target = make_url(url)
    db_name = target.database
    if not db_name:  # pragma: no cover - misconfiguration guard
        raise RuntimeError("TEST_DATABASE_URL must include a database name")

    admin_url = target.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            ).scalar()
            if not exists:
                # db_name comes from trusted config, not user input.
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Session-scoped engine bound to the provisioned test database.

    Also rebinds the app's shared ``SessionLocal`` to this engine for the test run,
    so code that opens its own session — the startup orphan sweeps the TestClient
    lifespan runs, and background job runners — uses the test database instead of
    the development ``DATABASE_URL``.
    """
    _ensure_database_exists(settings.TEST_DATABASE_URL)
    engine = create_engine(
        settings.TEST_DATABASE_URL, echo=False, pool_pre_ping=True
    )
    Base.metadata.create_all(engine)
    original_bind = SessionLocal.kw.get("bind")
    SessionLocal.configure(bind=engine)
    try:
        yield engine
    finally:
        SessionLocal.configure(bind=original_bind)
        engine.dispose()


def _seed_rebalance_prompt(session: Session) -> None:
    """Seed the active rebalance prompt, mirroring production's migration seed.

    In production the ``rebalance_prompt`` table always holds version 1 (seeded by
    migration); the test schema is built from the ORM models with no migrations, so
    seed it here for every DB-backed test. Seeded inside the test's rolled-back
    transaction. Tests exercising the empty-table path clear it explicitly.
    """
    from cadence.ai_portfolio.constants import PromptKind
    from cadence.ai_portfolio.models import RebalancePrompt

    session.add(
        RebalancePrompt(
            kind=PromptKind.REBALANCE.value,
            version=1,
            instructions=(
                "Rebalance instructions (test seed). "
                "caps: {max_new_assets}/{max_web_searches}"
            ),
            input_template=(
                "Rebalance {risk_profile} portfolio.\n"
                "Holdings:\n{holdings_json}\n"
                "Account:\n{account_json}\n"
                "Candidates:\n{candidates_json}\n"
            ),
        )
    )
    session.add(
        RebalancePrompt(
            kind=PromptKind.CRYPTO_REBALANCE.value,
            version=1,
            instructions=(
                "Crypto-only rebalance instructions (test seed). "
                "caps: {max_new_assets}/{max_web_searches}"
            ),
            input_template=(
                "Rebalance {risk_profile} crypto sleeve.\n"
                "Holdings:\n{holdings_json}\n"
                "Account:\n{account_json}\n"
                "Candidates:\n{candidates_json}\n"
            ),
        )
    )
    session.flush()


class _NullJournalSession:
    """Stand-in journal session for tests without a database: every write is dropped."""

    def add(self, *_args: object) -> None:
        return None

    def execute(self, *_args: object, **_kwargs: object) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _offline_news(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never call Alpaca News from tests, even with real keys in a local ``.env``."""
    monkeypatch.setattr(
        news_module.AlpacaNewsSource, "fetch_news", lambda self, *args, **kwargs: []
    )


@pytest.fixture(autouse=True)
def _fresh_environment_cache() -> Iterator[None]:
    """Forget cached account-mode probes so no test sees another's result."""
    environment.reset_cache()
    yield
    environment.reset_cache()


@pytest.fixture(autouse=True)
def _clean_order_journal(request: pytest.FixtureRequest) -> Iterator[None]:
    """Empty the order journal (and crashed-tick records) after every DB-backed test.

    The journal — like the record of a crashed bot tick — commits through its own
    sessions (so it survives the caller's rollback), which puts its rows outside the
    test's rolled-back transaction. Autouse
    fixtures are set up first and torn down last, so this runs after ``db_session`` has
    released any row lock it held on a journal row.
    """
    if "db_session" not in request.fixturenames:
        # No database in this test: journal writes go nowhere, so broker-only unit
        # tests (e.g. the AI executor) still exercise the gateway and its guard.
        monkeypatch: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
        monkeypatch.setattr(order_journal, "session_factory", _NullJournalSession)
        yield
        return
    engine: Engine = request.getfixturevalue("test_engine")
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM broker_orders"))
        conn.execute(text("DELETE FROM bot_tick_runs"))


@pytest.fixture
def db_session(test_engine: Engine) -> Iterator[Session]:
    """A session bound to a rolled-back outer transaction (savepoint mode)."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    _seed_rebalance_prompt(session)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """TestClient whose ``get_db`` yields the transactional session.

    The brokerage is stubbed by default (offline, deterministic) so add-time
    tradability lookups succeed without Alpaca credentials. Tests that need a
    different broker (e.g. an unconfigured one that 503s) override
    ``get_broker`` themselves.
    """

    def override_get_db() -> Iterator[Session]:
        yield db_session

    def override_get_broker() -> Broker:
        return StubBroker()

    def override_get_fundamentals_provider() -> FundamentalsProvider:
        # Offline by default: add-time stock fundamentals never hit SEC EDGAR.
        return FakeFundamentalsProvider()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_broker] = override_get_broker
    app.dependency_overrides[get_fundamentals_provider] = (
        override_get_fundamentals_provider
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
