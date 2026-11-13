"""Tests for the deployment environment identity and the trading guard."""

from __future__ import annotations

from typing import Any

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence import environment
from cadence.api.app import app
from cadence.api.routers.system import optional_broker
from cadence.broker.alpaca import LIVE_BASE_URL, PAPER_BASE_URL, AlpacaBroker
from cadence.broker.models import AccountMode
from cadence.broker.stub import StubBroker
from cadence.config import Settings, settings
from cadence.environment import TradingDisabledError
from cadence.orders.gateway import OrderGateway
from cadence.orders.models import BrokerOrder, OrderOwnerKind


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = "{}"

    def json(self) -> dict[str, Any]:
        return {}


class _ProbeSession:
    """Answers ``GET /v2/account`` per base URL; records every call."""

    def __init__(self, paper: int | Exception, live: int | Exception) -> None:
        self._answers = {PAPER_BASE_URL: paper, LIVE_BASE_URL: live}
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        self.calls.append((method, url))
        answer = next(a for base, a in self._answers.items() if url.startswith(base))
        if isinstance(answer, Exception):
            raise answer
        return _Response(answer)


def _alpaca(session: _ProbeSession, *, paper: bool = True) -> AlpacaBroker:
    return AlpacaBroker(api_key="k", secret_key="s", paper=paper, session=session)


class _ModeBroker(StubBroker):
    """A stub whose credentials belong to an account of the given mode."""

    def __init__(self, mode: AccountMode) -> None:
        super().__init__()
        self._mode = mode

    def probe_account_mode(self) -> AccountMode:
        return self._mode


# Settings ------------------------------------------------------------------------
def test_setting_defaults() -> None:
    fields = Settings.model_fields
    assert fields["CADENCE_ENVIRONMENT"].default == "QA"
    assert fields["ALPACA_ALLOW_LIVE"].default is False
    assert fields["ALPACA_PAPER"].default is True


# Probe ---------------------------------------------------------------------------
def test_probe_paper_keys_on_paper_config() -> None:
    session = _ProbeSession(paper=200, live=401)
    assert _alpaca(session).probe_account_mode() == "paper"
    assert session.calls == [("GET", f"{PAPER_BASE_URL}/v2/account")]


def test_probe_detects_live_keys_on_paper_config() -> None:
    session = _ProbeSession(paper=401, live=200)
    assert _alpaca(session).probe_account_mode() == "live"
    assert [method for method, _ in session.calls] == ["GET", "GET"]


def test_probe_live_config_checks_live_first() -> None:
    session = _ProbeSession(paper=200, live=200)
    assert _alpaca(session, paper=False).probe_account_mode() == "live"
    assert session.calls == [("GET", f"{LIVE_BASE_URL}/v2/account")]


@pytest.mark.parametrize(
    ("paper", "live"),
    [
        (401, 403),
        (500, 200),
        (requests.exceptions.ConnectionError("down"), 200),
    ],
)
def test_probe_unknown_when_no_endpoint_confirms(paper: Any, live: Any) -> None:
    assert _alpaca(_ProbeSession(paper=paper, live=live)).probe_account_mode() == "unknown"


def test_stub_is_paper() -> None:
    assert StubBroker().probe_account_mode() == "paper"


# Resolver ------------------------------------------------------------------------
def test_paper_qa_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CADENCE_ENVIRONMENT", "QA")
    monkeypatch.setattr(settings, "ALPACA_PAPER", True)

    status = environment.resolve_environment(_ModeBroker("paper"))

    assert status == environment.EnvironmentStatus(
        environment="QA",
        configured_mode="paper",
        account_mode="paper",
        mismatch=False,
        trading_enabled=True,
        reason=None,
    )


def test_mismatch_disables_trading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ALPACA_PAPER", True)

    status = environment.resolve_environment(_ModeBroker("live"))

    assert status.mismatch and not status.trading_enabled
    assert status.reason is not None and "live account" in status.reason


def test_live_needs_the_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ALPACA_PAPER", False)
    monkeypatch.setattr(settings, "ALPACA_ALLOW_LIVE", False)
    blocked = environment.resolve_environment(_ModeBroker("live"))
    assert not blocked.mismatch and not blocked.trading_enabled
    assert blocked.reason is not None and "ALPACA_ALLOW_LIVE" in blocked.reason

    monkeypatch.setattr(settings, "ALPACA_ALLOW_LIVE", True)
    assert environment.resolve_environment(_ModeBroker("live")).trading_enabled


def test_unknown_does_not_block() -> None:
    status = environment.resolve_environment(_ModeBroker("unknown"))
    assert (status.mismatch, status.trading_enabled) == (False, True)
    assert environment.resolve_environment(None).account_mode == "unknown"


def test_broker_without_probe_is_unknown() -> None:
    class _Bare:
        pass

    assert environment.account_mode(_Bare()) == "unknown"  # type: ignore[arg-type]


def test_alpaca_probe_is_cached_and_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1_000.0]
    monkeypatch.setattr(environment.time, "monotonic", lambda: clock[0])
    session = _ProbeSession(paper=200, live=401)
    broker = _alpaca(session)

    assert environment.account_mode(broker) == "paper"
    assert environment.account_mode(_alpaca(session)) == "paper"  # same credentials
    assert len(session.calls) == 1

    clock[0] += environment.CACHE_SECONDS + 1
    environment.account_mode(broker)
    assert len(session.calls) == 2


def test_unknown_is_cached_briefly(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [1_000.0]
    monkeypatch.setattr(environment.time, "monotonic", lambda: clock[0])
    session = _ProbeSession(paper=500, live=500)

    environment.account_mode(_alpaca(session))
    clock[0] += environment.UNKNOWN_CACHE_SECONDS + 1
    environment.account_mode(_alpaca(session))

    assert len(session.calls) == 2


# Guard ---------------------------------------------------------------------------
def test_guard_refuses_before_journal_or_broker(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ALPACA_PAPER", True)
    broker = _ModeBroker("live")
    gateway = OrderGateway(broker, owner_kind=OrderOwnerKind.ADMIN)

    with pytest.raises(TradingDisabledError, match="Trading disabled"):
        gateway.buy("AAPL", 1, purpose="admin_restore")
    with pytest.raises(TradingDisabledError):
        gateway.sell("AAPL", 1, purpose="admin_flatten")

    assert broker.get_open_orders() == []
    assert broker.get_positions() == []
    assert list(db_session.execute(select(BrokerOrder)).scalars()) == []


def test_guard_allows_a_matching_paper_account(db_session: Session) -> None:
    broker = _ModeBroker("paper")
    order = OrderGateway(broker, owner_kind=OrderOwnerKind.ADMIN).buy(
        "AAPL", 1, purpose="admin_restore"
    )
    assert order.client_order_id is not None


# Endpoint ------------------------------------------------------------------------
def test_environment_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CADENCE_ENVIRONMENT", "PRD")
    monkeypatch.setattr(settings, "ALPACA_PAPER", False)
    monkeypatch.setattr(settings, "ALPACA_ALLOW_LIVE", True)
    app.dependency_overrides[optional_broker] = lambda: _ModeBroker("live")
    try:
        resp = client.get("/api/v1/system/environment")
    finally:
        app.dependency_overrides.pop(optional_broker, None)

    assert resp.status_code == 200
    assert resp.json() == {
        "environment": "PRD",
        "configured_mode": "live",
        "account_mode": "live",
        "mismatch": False,
        "trading_enabled": True,
        "reason": None,
    }


def test_environment_endpoint_without_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ALPACA_STUB", False)
    monkeypatch.setattr(settings, "ALPACA_API_KEY", "")

    resp = client.get("/api/v1/system/environment")

    assert resp.status_code == 200
    body = resp.json()
    assert body["account_mode"] == "unknown"
    assert "key" not in str(body).lower()
