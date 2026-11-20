"""Tests for Keycloak token validation and per-route authorization.

Tokens are minted locally with a generated RSA key; the JWKS lookup is replaced so no
network is involved.
"""

from __future__ import annotations

import re
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from cadence import auth
from cadence.api.app import app
from cadence.config import settings

_ISSUER = "https://cadence.test:8443/auth/realms/cadence"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeJwks:
    uri = "fake"

    class _Key:
        key = _KEY.public_key()

    def get_signing_key_from_jwt(self, token: str) -> Any:
        return self._Key()


def _token(
    *roles: str,
    key: Any = _KEY,
    aud: str = "cadence-api",
    iss: str = _ISSUER,
    exp_in: int = 300,
    sub: str = "user-1",
    username: str = "nils",
) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "preferred_username": username,
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + exp_in,
        "realm_access": {"roles": list(roles)},
    }
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def auth_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "OIDC_ISSUER", _ISSUER)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", "cadence-api")
    monkeypatch.setattr(auth, "jwks_client", lambda: _FakeJwks())


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# Unit ------------------------------------------------------------------------------
def test_settings_defaults() -> None:
    fields = type(settings).model_fields
    assert fields["AUTH_ENABLED"].default is True
    assert fields["OIDC_AUDIENCE"].default == "cadence-api"


def test_issuer_derived_from_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OIDC_ISSUER", "")
    monkeypatch.setattr(settings, "CADENCE_PUBLIC_URL", "https://pi.local:9443/")
    assert auth.oidc_issuer() == "https://pi.local:9443/auth/realms/cadence"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (["viewer"], {"viewer"}),
        (["trader"], {"trader", "viewer"}),
        (["admin"], {"admin", "trader", "viewer"}),
        (["offline_access", "uma_authorization"], set()),
        (None, set()),
    ],
)
def test_role_hierarchy(raw: Any, expected: set[str]) -> None:
    assert auth.expand_roles(raw) == frozenset(expected)


@pytest.mark.parametrize(
    ("method", "path", "role"),
    [
        ("GET", "/api/v1/bots/sessions", "viewer"),
        ("POST", "/api/v1/bots/sessions", "trader"),
        ("DELETE", "/api/v1/portfolios/{portfolio_id}", "trader"),
        ("GET", "/api/v1/admin/account", "admin"),
        ("POST", "/api/v1/admin/flatten-orphans", "admin"),
        ("POST", "/api/v1/assets", "admin"),
        ("DELETE", "/api/v1/assets/{asset_id}", "admin"),
        ("POST", "/api/v1/assets/universe-evaluation/refresh", "admin"),
        ("POST", "/api/v1/recommendations", "admin"),
        ("GET", "/api/v1/recommendations", "viewer"),
        ("GET", "/api/v1/assets", "viewer"),
        # Router-relative templates (how FastAPI 0.141 reports included routes).
        ("POST", "/admin/reconcile-orders", "admin"),
        ("POST", "/assets", "admin"),
        ("GET", "/assets/{asset_id}", "viewer"),
        ("POST", "/bots/sessions", "trader"),
    ],
)
def test_required_role(method: str, path: str, role: str) -> None:
    assert auth.required_role(method, path) == role


def test_decode_valid_token(auth_on: None) -> None:
    user = auth.decode_token(_token("trader"))
    assert (user.sub, user.username) == ("user-1", "nils")
    assert user.roles == frozenset({"trader", "viewer"})


@pytest.mark.parametrize(
    "token_kwargs",
    [
        {"exp_in": -10},
        {"aud": "another-api"},
        {"iss": "https://evil.example/auth/realms/cadence"},
        {"key": _OTHER_KEY},
    ],
)
def test_invalid_tokens_are_rejected(auth_on: None, token_kwargs: dict[str, Any]) -> None:
    with pytest.raises(auth.HTTPException) as exc:
        auth.decode_token(_token("admin", **token_kwargs))
    assert exc.value.status_code == 401


# API -------------------------------------------------------------------------------
def test_no_token_is_401(client: TestClient, auth_on: None) -> None:
    resp = client.get("/api/v1/portfolios")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


def test_garbage_token_is_401(client: TestClient, auth_on: None) -> None:
    assert client.get("/api/v1/portfolios", headers=_bearer("nope")).status_code == 401


def test_viewer_reads_but_cannot_act(client: TestClient, auth_on: None) -> None:
    viewer = _bearer(_token("viewer"))
    assert client.get("/api/v1/portfolios", headers=viewer).status_code == 200
    resp = client.post("/api/v1/portfolios", json={"name": "x", "stocks": ["AAPL"]}, headers=viewer)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "You don't have permission for this action"


def test_user_without_role_is_403(client: TestClient, auth_on: None) -> None:
    assert client.get("/api/v1/portfolios", headers=_bearer(_token())).status_code == 403


def test_trader_cannot_use_admin_or_universe(client: TestClient, auth_on: None) -> None:
    trader = _bearer(_token("trader"))
    assert client.post("/api/v1/admin/reconcile-orders", headers=trader).status_code == 403
    resp = client.post("/api/v1/assets", json={"ticker": "AAPL"}, headers=trader)
    assert resp.status_code == 403


def test_admin_passes_the_role_check(client: TestClient, auth_on: None) -> None:
    resp = client.post("/api/v1/admin/reconcile-orders", headers=_bearer(_token("admin")))
    assert resp.status_code not in (401, 403)


def test_health_is_open(client: TestClient, auth_on: None) -> None:
    assert client.get("/health").status_code == 200


def test_cron_route_uses_its_token_not_a_login(
    client: TestClient, auth_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    resp = client.post("/api/v1/bots/snapshot-daily", headers={"X-Cron-Token": "secret"})
    assert resp.status_code == 200
    # Without the cron token it is still refused by the cron guard (403), not by login.
    assert client.post("/api/v1/bots/snapshot-daily").status_code == 403


def test_current_user_is_available_on_the_request(auth_on: None) -> None:
    from starlette.requests import Request

    request = Request({"type": "http", "headers": [], "state": {}})
    request.state.user = auth.AuthUser(sub="s", username="u", roles=frozenset({"viewer"}))
    assert auth.get_current_user(request) == request.state.user


def test_every_route_is_guarded(client: TestClient, auth_on: None) -> None:
    """No route other than health and cron routes may answer without a token.

    Routes come from the OpenAPI schema (FastAPI 0.141 keeps included routers nested).
    A cron route is refused by its own cron guard (403 with the cron-token detail).
    """
    paths = app.openapi()["paths"]
    open_routes: list[str] = []
    checked = 0
    for template, operations in paths.items():
        if template == "/health":
            continue
        concrete = re.sub(r"\{[^}]+\}", "1", template)
        for method in operations:
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            checked += 1
            resp = client.request(method.upper(), concrete)
            cron_guarded = (
                resp.status_code == 403
                and resp.json().get("detail") == "Invalid or missing cron token"
            )
            if resp.status_code != 401 and not cron_guarded:
                open_routes.append(f"{method.upper()} {template} -> {resp.status_code}")
    assert checked > 80
    assert open_routes == []
