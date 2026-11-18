"""Structure checks for the versioned Keycloak realm import (no Keycloak needed)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_REALM = Path(__file__).resolve().parents[2] / "keycloak" / "cadence-realm.json"


@pytest.fixture(scope="module")
def realm() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_REALM.read_text())
    return data


def _client(realm: dict[str, Any]) -> dict[str, Any]:
    [client] = [c for c in realm["clients"] if c["clientId"] == "cadence-web"]
    return client


def test_realm_basics(realm: dict[str, Any]) -> None:
    assert realm["realm"] == "cadence"
    assert realm["registrationAllowed"] is False
    assert realm["bruteForceProtected"] is True
    assert "length(12)" in realm["passwordPolicy"]
    assert realm["accessTokenLifespan"] <= 300
    assert "users" not in realm  # no built-in accounts or default passwords


def test_role_hierarchy(realm: dict[str, Any]) -> None:
    roles = {r["name"]: r for r in realm["roles"]["realm"]}
    assert set(roles) == {"viewer", "trader", "admin"}
    assert roles["trader"]["composites"]["realm"] == ["viewer"]
    assert roles["admin"]["composites"]["realm"] == ["trader"]
    assert not roles["viewer"].get("composite", False)


def test_web_client_is_public_pkce_only(realm: dict[str, Any]) -> None:
    client = _client(realm)
    assert client["publicClient"] is True
    assert client["standardFlowEnabled"] is True
    assert client["implicitFlowEnabled"] is False
    assert client["directAccessGrantsEnabled"] is False
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"
    assert client["redirectUris"] == ["${CADENCE_PUBLIC_URL}/*"]
    assert client["webOrigins"] == ["${CADENCE_PUBLIC_URL}"]


def test_access_tokens_carry_the_api_audience(realm: dict[str, Any]) -> None:
    [mapper] = [
        m
        for m in _client(realm)["protocolMappers"]
        if m["protocolMapper"] == "oidc-audience-mapper"
    ]
    assert mapper["config"]["included.custom.audience"] == "cadence-api"
    assert mapper["config"]["access.token.claim"] == "true"
