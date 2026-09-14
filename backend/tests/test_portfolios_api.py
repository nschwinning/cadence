"""TestClient tests for the portfolios API."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_valid(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/portfolios",
        json={
            "name": "Growth",
            "stocks": [" aapl ", "MSFT", "aapl"],
            "source": "manual",
            "risk_profile": "balanced",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Growth"
    assert body["stocks"] == ["AAPL", "MSFT"]
    assert body["source"] == "manual"
    assert body["risk_profile"] == "balanced"
    assert body["max_allocation_pct"] == 1.0


def test_create_rejects_empty_tickers(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/portfolios",
        json={"name": "Empty", "stocks": ["", "   "]},
    )
    assert resp.status_code == 422


def test_create_defaults_to_manual_source(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/portfolios", json={"name": "P", "stocks": ["AAPL"]}
    )
    assert resp.status_code == 201
    assert resp.json()["source"] == "manual"


def test_list_and_get(client: TestClient) -> None:
    created = client.post(
        "/api/v1/portfolios", json={"name": "P", "stocks": ["AAPL"]}
    ).json()
    portfolio_id = created["id"]

    listed = client.get("/api/v1/portfolios")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1
    assert any(item["id"] == portfolio_id for item in body["items"])

    fetched = client.get(f"/api/v1/portfolios/{portfolio_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == portfolio_id


def test_get_unknown_returns_404(client: TestClient) -> None:
    import uuid

    resp = client.get(f"/api/v1/portfolios/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_malformed_id_returns_422(client: TestClient) -> None:
    resp = client.get("/api/v1/portfolios/not-a-uuid")
    assert resp.status_code == 422
