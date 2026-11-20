"""Tests for user accounts, data ownership and visibility.

Three signed-in users: traders Alice and Bob, and an admin. Tokens are minted with the
local signing key from ``tests.test_auth`` (``auth_on`` switches authentication on).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_auth import _token, auth_on  # noqa: F401  (fixture)

from cadence.accounts.models import LEGACY_OWNER_ID, User
from cadence.accounts.service import resolve_user
from cadence.ai_portfolio import events as ai_events
from cadence.ai_portfolio.models import AIPortfolioEvent
from cadence.api.app import app
from cadence.assets.models import Asset
from cadence.auth import AuthUser
from cadence.bot_orchestrator import runs as orchestrator_runs
from cadence.bot_orchestrator import service as orchestrator_service
from cadence.bot_orchestrator.constants import OrchestratorTrigger
from cadence.broker.stub import StubBroker
from cadence.config import settings
from cadence.orders.gateway import OrderGateway
from cadence.orders.models import BrokerOrder, OrderOwnerKind
from cadence.paper_trading.models import PaperTradingSession
from cadence.portfolios import service as portfolios_service
from cadence.strategy_bots import service as bot_service

ALICE = {"sub": "sub-alice", "name": "alice"}
BOB = {"sub": "sub-bob", "name": "bob"}
ROOT = {"sub": "sub-root", "name": "root"}


def _headers(user: dict[str, str], role: str) -> dict[str, str]:
    token = _token(role, sub=user["sub"], username=user["name"])
    return {"Authorization": f"Bearer {token}"}


def _alice() -> dict[str, str]:
    return _headers(ALICE, "trader")


def _bob() -> dict[str, str]:
    return _headers(BOB, "trader")


def _admin() -> dict[str, str]:
    return _headers(ROOT, "admin")


def _user_id(db: Session, sub: str) -> uuid.UUID:
    return db.execute(select(User.id).where(User.keycloak_sub == sub)).scalar_one()


@pytest.fixture
def asset(db_session: Session) -> Asset:
    row = Asset(
        ticker="AAPL",
        name="Apple",
        sector="technology",
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db_session.add(row)
    db_session.flush()
    return row


@pytest.fixture
def users(client: TestClient, auth_on: None, db_session: Session) -> dict[str, uuid.UUID]:  # noqa: F811
    """Sign each user in once so their accounts exist."""
    for headers in (_alice(), _bob(), _admin()):
        assert client.get("/api/v1/portfolios", headers=headers).status_code == 200
    return {
        "alice": _user_id(db_session, ALICE["sub"]),
        "bob": _user_id(db_session, BOB["sub"]),
        "root": _user_id(db_session, ROOT["sub"]),
    }


@pytest.fixture
def alice_data(
    db_session: Session, users: dict[str, uuid.UUID], asset: Asset
) -> dict[str, uuid.UUID]:
    """One of each owned object, belonging to Alice."""
    owner = users["alice"]
    portfolio = portfolios_service.create_portfolio(
        db_session, name="Alice P", stocks=["AAPL"], owner_user_id=owner
    )
    session = PaperTradingSession(
        portfolio_id=portfolio.id,
        strategy_key="ai_buy_hold",
        rebalance_prompt_version=1,
        crypto_rebalance_prompt_version=1,
        status="active",
    )
    db_session.add(session)
    db_session.flush()
    event = AIPortfolioEvent(
        event_type="rebalance", status="succeeded", session_id=session.id, owner_user_id=owner
    )
    db_session.add(event)
    bot = bot_service.create_bot_session(
        db_session,
        strategy_key="ma_crossover",
        tickers=["AAPL"],
        initial_capital=10_000.0,
        benchmark="SP500",
        strategy_params={"fast_period": 2, "slow_period": 3},
        owner_user_id=owner,
    )
    orchestrator = orchestrator_service.create_orchestrator(
        db_session, label="Alice O", capital=10_000.0, owner_user_id=owner
    )
    run = orchestrator_runs.queue_run(db_session, orchestrator, OrchestratorTrigger.MANUAL)
    db_session.flush()
    return {
        "portfolio_id": portfolio.id,
        "session_id": session.id,
        "event_id": event.id,
        "bot_id": bot.id,
        "orchestrator_id": orchestrator.id,
        "run_id": run.id,
    }


# Accounts --------------------------------------------------------------------------
def _auth_user(sub: str, username: str) -> AuthUser:
    return AuthUser(sub=sub, username=username, roles=frozenset({"viewer"}))


def test_first_sign_in_creates_and_then_finds_the_account(db_session: Session) -> None:
    first = resolve_user(db_session, _auth_user("sub-x", "xavier"))
    again = resolve_user(db_session, _auth_user("sub-x", "xavier-renamed"))
    assert again.id == first.id
    assert again.username == "xavier-renamed"
    assert first.id != LEGACY_OWNER_ID


def test_legacy_owner_links_once_by_username(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CADENCE_LEGACY_OWNER", "nils")

    linked = resolve_user(db_session, _auth_user("sub-nils", "nils"))
    assert linked.id == LEGACY_OWNER_ID
    assert linked.keycloak_sub == "sub-nils"

    # Another account with the same username later: its own, empty account.
    other = resolve_user(db_session, _auth_user("sub-nils-2", "nils"))
    assert other.id != LEGACY_OWNER_ID
    # The linked owner keeps its link.
    assert resolve_user(db_session, _auth_user("sub-nils", "nils")).id == LEGACY_OWNER_ID


def test_users_signing_in_before_the_legacy_owner_get_their_own_account(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CADENCE_LEGACY_OWNER", "nils")
    early = resolve_user(db_session, _auth_user("sub-eve", "eve"))
    assert early.id != LEGACY_OWNER_ID
    legacy = db_session.get(User, LEGACY_OWNER_ID)
    assert legacy is not None and legacy.keycloak_sub is None


def test_no_legacy_owner_configured_never_links(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CADENCE_LEGACY_OWNER", "")
    assert resolve_user(db_session, _auth_user("sub-y", "")).id != LEGACY_OWNER_ID


def test_auth_disabled_acts_as_the_legacy_owner(client: TestClient, db_session: Session) -> None:
    resp = client.post("/api/v1/portfolios", json={"name": "Dev P", "stocks": ["AAPL"]})
    assert resp.status_code == 201
    assert resp.json()["owner_user_id"] == str(LEGACY_OWNER_ID)


# Ownership on creation -------------------------------------------------------------
def test_created_objects_belong_to_their_creator(
    client: TestClient, users: dict[str, uuid.UUID], asset: Asset
) -> None:
    alice = str(users["alice"])
    portfolio = client.post(
        "/api/v1/portfolios", json={"name": "Mine", "stocks": ["AAPL"]}, headers=_alice()
    )
    bot = client.post(
        "/api/v1/bots/sessions",
        json={
            "strategy_key": "ma_crossover",
            "tickers": ["AAPL"],
            "initial_capital": 10_000.0,
            "benchmark": "SP500",
            "strategy_params": {"fast_period": 2, "slow_period": 3},
        },
        headers=_alice(),
    )
    orchestrator = client.post(
        "/api/v1/bot-orchestrators",
        json={"label": "Mine", "capital": 10_000.0},
        headers=_alice(),
    )
    for resp in (portfolio, bot, orchestrator):
        assert resp.status_code == 201, resp.text
        assert (resp.json()["owner_user_id"], resp.json()["owner"]) == (alice, "alice")


def test_orchestrator_bots_belong_to_the_orchestrator_owner(
    db_session: Session, users: dict[str, uuid.UUID], asset: Asset
) -> None:
    orchestrator = orchestrator_service.create_orchestrator(
        db_session, label="O", capital=10_000.0, owner_user_id=users["alice"]
    )
    bot = bot_service.create_bot_session(
        db_session,
        preset_key="ma_crossover_algo6",
        tickers=["AAPL"],
        initial_capital=5_000.0,
        benchmark="SP500",
        orchestrator_id=orchestrator.id,
    )
    assert bot.owner_user_id == users["alice"]


def test_ai_events_belong_to_the_session_owner(
    db_session: Session, alice_data: dict[str, uuid.UUID], users: dict[str, uuid.UUID]
) -> None:
    rebalance = ai_events.create_rebalance_event(db_session, alice_data["session_id"])
    close = ai_events.create_close_event(db_session, alice_data["session_id"])
    assert rebalance.owner_user_id == close.owner_user_id == users["alice"]


class _SameTransaction:
    """Routes the journal's independent writes through the test's own session.

    In production the journal writes in its own committed session; here the users only
    exist inside the test's (rolled-back) transaction, which another session cannot see.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def __getattr__(self, name: str) -> Any:
        return getattr(self._db, name)

    def close(self) -> None:
        return None


def test_order_journal_records_the_account(
    db_session: Session,
    alice_data: dict[str, uuid.UUID],
    users: dict[str, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cadence.orders import journal

    monkeypatch.setattr(journal, "session_factory", lambda: _SameTransaction(db_session))
    broker = StubBroker()
    # The bot engine's gateway carries the bot owner's account.
    from cadence.strategy_bots.engine import ExecutionEngine
    from cadence.strategy_bots.models import BotSession

    bot = db_session.get(BotSession, alice_data["bot_id"])
    assert bot is not None
    bot_order = ExecutionEngine(db_session, broker)._gateway(bot).buy("AAPL", 1, purpose="entry")
    # The AI executor passes the session owner's account (looked up by the caller).
    from cadence.accounts.lookups import session_owner_id

    ai_order = OrderGateway(
        broker,
        owner_kind=OrderOwnerKind.AI_SESSION,
        owner_id=alice_data["session_id"],
        account_user_id=session_owner_id(db_session, alice_data["session_id"]),
    ).buy("AAPL", 1, purpose="rebalance")
    admin_order = OrderGateway(
        broker, owner_kind=OrderOwnerKind.ADMIN, account_user_id=users["root"]
    ).buy("AAPL", 1, purpose="admin_restore")

    def account(client_order_id: str | None) -> uuid.UUID:
        return db_session.execute(
            select(BrokerOrder.account_user_id).where(
                BrokerOrder.client_order_id == client_order_id
            )
        ).scalar_one()

    assert account(bot_order.client_order_id) == users["alice"]
    assert account(ai_order.client_order_id) == users["alice"]
    assert account(admin_order.client_order_id) == users["root"]


# Visibility -------------------------------------------------------------------------
def test_lists_show_only_own_objects(client: TestClient, alice_data: dict[str, uuid.UUID]) -> None:
    for path in (
        "/api/v1/portfolios",
        "/api/v1/bots/sessions",
        "/api/v1/bot-orchestrators",
        "/api/v1/paper-trading/sessions",
        "/api/v1/ai-portfolio/runs",
    ):
        mine = client.get(path, headers=_alice()).json()["items"]
        theirs = client.get(path, headers=_bob()).json()["items"]
        assert len(mine) == 1, path
        assert theirs == [], path


def test_all_users_scope_is_admin_only(
    client: TestClient, alice_data: dict[str, uuid.UUID]
) -> None:
    assert client.get("/api/v1/bots/sessions?scope=all", headers=_bob()).status_code == 403
    admin_mine = client.get("/api/v1/bots/sessions", headers=_admin()).json()["items"]
    admin_all = client.get("/api/v1/bots/sessions?scope=all", headers=_admin()).json()["items"]
    assert admin_mine == []
    assert [b["owner"] for b in admin_all] == ["alice"]


def test_dashboard_covers_own_data(client: TestClient, alice_data: dict[str, uuid.UUID]) -> None:
    alice = client.get("/api/v1/dashboard/metrics", headers=_alice()).json()
    bob = client.get("/api/v1/dashboard/metrics", headers=_bob()).json()
    assert (alice["portfolio_count"], bob["portfolio_count"]) == (1, 0)
    assert alice["paper_trading"]["active_sessions"] == 1
    assert bob["paper_trading"]["active_sessions"] == 0


def test_recommendation_runs_are_admin_only(
    client: TestClient, users: dict[str, uuid.UUID]
) -> None:
    resp = client.post("/api/v1/recommendations", json={"count": 3}, headers=_alice())
    assert resp.status_code == 403


_PARAM_IDS = {
    "portfolio_id": "portfolio_id",
    "event_id": "event_id",
    "orchestrator_id": "orchestrator_id",
    "run_id": "run_id",
}


def _owned_routes(alice: dict[str, uuid.UUID]) -> list[tuple[str, str]]:
    """Every user-facing route addressing one of Alice's objects, with ids filled in."""
    routes: list[tuple[str, str]] = []
    for template, operations in app.openapi()["paths"].items():
        params = re.findall(r"\{([^}]+)\}", template)
        if not params or template.startswith("/api/v1/recommendations"):
            continue  # recommendation runs are shared, not owned
        values: dict[str, uuid.UUID] = {}
        for name in params:
            if name == "session_id":
                key = "bot_id" if template.startswith("/api/v1/bots/") else "session_id"
                values[name] = alice[key]
            elif name in _PARAM_IDS:
                values[name] = alice[_PARAM_IDS[name]]
        if len(values) != len(params):
            continue  # not an owned-object route (e.g. assets)
        path = template
        for name, value in values.items():
            path = path.replace("{" + name + "}", str(value))
        for method, operation in operations.items():
            parameters = operation.get("parameters", [])
            if any(p.get("name") == "x-cron-token" for p in parameters):
                continue
            routes.append((method.upper(), path))
    return routes


def test_other_users_objects_are_invisible(
    client: TestClient, alice_data: dict[str, uuid.UUID]
) -> None:
    """As Bob, every route addressing Alice's objects answers 404 — reads and actions."""
    routes = _owned_routes(alice_data)
    assert len(routes) >= 30
    leaks = [
        f"{method} {path} -> {resp.status_code}"
        for method, path in routes
        if (resp := client.request(method, path, headers=_bob(), json={})).status_code != 404
    ]
    assert leaks == []


def test_admin_reads_everything_but_cannot_act_on_others(
    client: TestClient, alice_data: dict[str, uuid.UUID]
) -> None:
    problems: list[str] = []
    for method, path in _owned_routes(alice_data):
        resp = client.request(method, path, headers=_admin(), json={})
        if method == "GET" and resp.status_code in (401, 403, 404):
            problems.append(f"read {path} -> {resp.status_code}")
        if method != "GET" and resp.status_code != 403:
            problems.append(f"act {method} {path} -> {resp.status_code}")
    assert problems == []


def test_owner_acts_on_own_object(client: TestClient, alice_data: dict[str, uuid.UUID]) -> None:
    resp = client.post(f"/api/v1/bots/sessions/{alice_data['bot_id']}/stop", headers=_alice())
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


def test_detail_shows_the_owner(client: TestClient, alice_data: dict[str, uuid.UUID]) -> None:
    body: dict[str, Any] = client.get(
        f"/api/v1/bot-orchestrators/{alice_data['orchestrator_id']}", headers=_admin()
    ).json()
    assert body["owner"] == "alice"


def test_me_returns_the_signed_in_account(
    client: TestClient, users: dict[str, uuid.UUID]
) -> None:
    alice = client.get("/api/v1/me", headers=_alice()).json()
    admin = client.get("/api/v1/me", headers=_admin()).json()
    assert alice == {"user_id": str(users["alice"]), "username": "alice", "is_admin": False}
    assert admin["is_admin"] is True


def test_me_without_auth_is_the_legacy_owner(client: TestClient) -> None:
    assert client.get("/api/v1/me").json()["user_id"] == str(LEGACY_OWNER_ID)

