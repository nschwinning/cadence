"""API tests for the read-only system-status endpoint.

``GET /api/v1/system/status`` is a plain, unauthenticated GET that live-probes
each external backend. It must always return 200 with one entry per backend —
even when a probe fails — and must never leak a secret value into the payload.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cadence.config import settings
from cadence.system import service

# Expected backend names, mirroring the service probe registry.
_EXPECTED_BACKENDS = {"Alpaca", "Web search", "yfinance", "OpenAI"}

# Distinctive fake secret values we plant in settings and then assert never
# appear anywhere in the serialized response body.
_FAKE_SECRETS = {
    "ALPACA_API_KEY": "SECRET-alpaca-key-DEADBEEF",
    "ALPACA_SECRET_KEY": "SECRET-alpaca-secret-DEADBEEF",
    "SERP_API_KEY": "SECRET-serp-key-DEADBEEF",
    "SERPER_API_KEY": "SECRET-serper-key-DEADBEEF",
    "OPENAI_API_KEY": "SECRET-openai-key-DEADBEEF",
}


def _no_network_probes() -> tuple[tuple[str, object], ...]:
    """A probe registry with a raising probe plus fast healthy ones (no network)."""

    def _raises() -> service.ProbeResult:
        raise RuntimeError("probe blew up")

    def _ok(name: str) -> service.ProbeResult:
        return service.ProbeResult(
            name=name, configured=True, identifier=name, reachable=True, latency_ms=1.0
        )

    return (
        ("Alpaca", _raises),
        ("Web search", lambda: _ok("Web search")),
        ("yfinance", lambda: _ok("yfinance")),
        ("OpenAI", lambda: _ok("OpenAI")),
    )


def test_status_returns_200_with_entry_per_backend_when_a_probe_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "_PROBES", _no_network_probes())

    response = client.get("/api/v1/system/status")

    assert response.status_code == 200
    body = response.json()
    names = {b["name"] for b in body["backends"]}
    assert names == _EXPECTED_BACKENDS

    by_name = {b["name"]: b for b in body["backends"]}
    # The failing probe is isolated: marked unreachable, others unaffected.
    assert by_name["Alpaca"]["reachable"] is False
    assert by_name["yfinance"]["reachable"] is True


def test_status_never_exposes_secret_values(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for attr, value in _FAKE_SECRETS.items():
        monkeypatch.setattr(settings, attr, value)
    # Keep the broker offline (stub) and avoid real network from any probe.
    monkeypatch.setattr(settings, "ALPACA_STUB", True)
    monkeypatch.setattr(service, "_PROBES", _no_network_probes())

    response = client.get("/api/v1/system/status")

    assert response.status_code == 200
    raw = response.text
    for value in _FAKE_SECRETS.values():
        assert value not in raw
