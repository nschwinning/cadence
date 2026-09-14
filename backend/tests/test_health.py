"""Smoke test for the health endpoint.

No database is running in the test environment, so we assert only on the shape
and enum validity of the response, not on a "connected" value.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from cadence.api.app import app

client = TestClient(app)


def test_health_returns_200_with_valid_shape() -> None:
    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"status", "database"}
    assert body["status"] in {"ok", "degraded"}
    assert body["database"] in {"connected", "disconnected"}
