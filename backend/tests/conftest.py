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
from cadence.ai_portfolio import models as _ai_portfolio_models  # noqa: F401
from cadence.api.app import app
from cadence.assets import models as _assets_models  # noqa: F401
from cadence.broker import Broker, get_broker
from cadence.broker.stub import StubBroker
from cadence.config import settings
from cadence.database import Base, get_db
from cadence.paper_trading import models as _paper_trading_models  # noqa: F401
from cadence.portfolios import models as _portfolios_models  # noqa: F401
from cadence.recommendations import models as _recommendations_models  # noqa: F401


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
    """Session-scoped engine bound to the provisioned test database."""
    _ensure_database_exists(settings.TEST_DATABASE_URL)
    engine = create_engine(
        settings.TEST_DATABASE_URL, echo=False, pool_pre_ping=True
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _seed_rebalance_prompt(session: Session) -> None:
    """Seed the active rebalance prompt, mirroring production's migration seed.

    In production the ``rebalance_prompt`` table always holds version 1 (seeded by
    migration); the test schema is built from the ORM models with no migrations, so
    seed it here for every DB-backed test. Seeded inside the test's rolled-back
    transaction. Tests exercising the empty-table path clear it explicitly.
    """
    from cadence.ai_portfolio.models import RebalancePrompt

    session.add(
        RebalancePrompt(
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
    session.flush()


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

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_broker] = override_get_broker
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
