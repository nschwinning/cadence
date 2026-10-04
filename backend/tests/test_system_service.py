"""Unit tests for the system-status probe service.

Probes are exercised without touching the network: stub/unconfigured branches
return early, and the configured branches are driven through monkeypatched seams
(injected provider, patched search function / OpenAI client factory). Each test
also guards the invariant that a probe never raises.
"""

from __future__ import annotations

import time

import pytest

from cadence.assets.market_data import AssetInfo
from cadence.config import settings
from cadence.system import service

# --- Alpaca ------------------------------------------------------------------


def test_alpaca_stub_mode_makes_no_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ALPACA_STUB", True)

    # Any attempt to build a broker would be a bug in stub mode.
    def _boom() -> object:  # pragma: no cover - must never be called
        raise AssertionError("stub mode must not construct a broker")

    monkeypatch.setattr("cadence.broker.AlpacaBroker", _boom)

    result = service.probe_alpaca()

    assert result.configured is True
    assert result.identifier == "stub"
    assert result.reachable is None
    assert result.latency_ms is None


def test_alpaca_blank_creds_report_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ALPACA_STUB", False)
    monkeypatch.setattr(settings, "ALPACA_API_KEY", "")
    monkeypatch.setattr(settings, "ALPACA_SECRET_KEY", "")
    monkeypatch.setattr(settings, "ALPACA_PAPER", True)

    result = service.probe_alpaca()

    assert result.configured is False
    assert result.identifier == "paper"
    assert result.reachable is None


# --- Web search --------------------------------------------------------------


def test_web_search_reachable_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "serpapi")
    monkeypatch.setattr(settings, "SERP_API_KEY", "test-key")
    monkeypatch.setattr(
        "cadence.agents.tools._search_serpapi",
        lambda query: {"organic_results": [{"title": "ok"}]},
    )

    result = service.probe_web_search()

    assert result.configured is True
    assert result.identifier == "serpapi"
    assert result.reachable is True
    assert result.latency_ms is not None


def test_web_search_unreachable_on_error_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "serper")
    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(
        "cadence.agents.tools._search_serper",
        lambda query: {"error": "Serper returned HTTP 500"},
    )

    result = service.probe_web_search()

    assert result.reachable is False
    assert result.detail == "error"


def test_web_search_unconfigured_is_not_probed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "serpapi")
    monkeypatch.setattr(settings, "SERP_API_KEY", "")

    result = service.probe_web_search()

    assert result.configured is False
    assert result.reachable is None


# --- yfinance ----------------------------------------------------------------


class _FakeProvider:
    """Minimal MarketDataProvider stand-in for the yfinance probe."""

    def __init__(self, *, raise_exc: Exception | None = None) -> None:
        self._raise = raise_exc

    def fetch_info(self, ticker: str) -> AssetInfo:
        if self._raise is not None:
            raise self._raise
        return AssetInfo(
            company_name="SPDR S&P 500 ETF Trust",
            exchange="ARCA",
            currency="USD",
            price=500.0,
            market_cap=None,
            quote_type="ETF",
        )


def test_yfinance_reachable_on_data() -> None:
    result = service.probe_yfinance(provider=_FakeProvider())

    assert result.configured is True
    assert result.identifier == "yfinance"
    assert result.reachable is True
    assert result.latency_ms is not None


def test_yfinance_unreachable_on_raise() -> None:
    result = service.probe_yfinance(
        provider=_FakeProvider(raise_exc=RuntimeError("boom"))
    )

    assert result.reachable is False
    assert result.detail is not None


# --- OpenAI ------------------------------------------------------------------


class _FakeModels:
    def __init__(self, *, raise_exc: Exception | None = None) -> None:
        self._raise = raise_exc

    def retrieve(self, model: str) -> object:
        if self._raise is not None:
            raise self._raise
        return object()


class _FakeOpenAIClient:
    def __init__(self, *, raise_exc: Exception | None = None) -> None:
        self.models = _FakeModels(raise_exc=raise_exc)


def test_openai_reachable_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(service, "_build_openai_client", lambda: _FakeOpenAIClient())

    result = service.probe_openai()

    assert result.configured is True
    assert result.identifier == settings.AI_PORTFOLIO_MODEL
    assert result.reachable is True
    assert result.latency_ms is not None


def test_openai_unreachable_with_auth_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-bad")

    class AuthenticationError(Exception):
        pass

    monkeypatch.setattr(
        service,
        "_build_openai_client",
        lambda: _FakeOpenAIClient(raise_exc=AuthenticationError("invalid api key")),
    )

    result = service.probe_openai()

    assert result.reachable is False
    assert result.detail == "unauthorized"


def test_openai_unconfigured_is_not_probed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    result = service.probe_openai()

    assert result.configured is False
    assert result.reachable is None


# --- Aggregator --------------------------------------------------------------


def test_get_system_status_bounds_a_slow_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SYSTEM_STATUS_PROBE_TIMEOUT_SECONDS", 0.2)

    def _slow() -> service.ProbeResult:
        time.sleep(5)  # well past the timeout
        return service.ProbeResult(name="Alpaca", configured=True, reachable=True)

    def _fast() -> service.ProbeResult:
        return service.ProbeResult(
            name="yfinance", configured=True, reachable=True, latency_ms=1.0
        )

    monkeypatch.setattr(
        service,
        "_PROBES",
        (("Alpaca", _slow), ("yfinance", _fast)),
    )

    start = time.perf_counter()
    status = service.get_system_status()
    elapsed = time.perf_counter() - start

    # Bounded by roughly the single timeout, not the 5s sleep.
    assert elapsed < 2.0

    by_name = {b.name: b for b in status.backends}
    assert set(by_name) == {"Alpaca", "yfinance"}
    assert by_name["Alpaca"].reachable is False
    assert by_name["Alpaca"].detail == "timeout"
    assert by_name["yfinance"].reachable is True


def test_get_system_status_isolates_a_raising_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raises() -> service.ProbeResult:
        raise RuntimeError("kaboom")

    def _ok() -> service.ProbeResult:
        return service.ProbeResult(name="yfinance", configured=True, reachable=True)

    monkeypatch.setattr(
        service,
        "_PROBES",
        (("Alpaca", _raises), ("yfinance", _ok)),
    )

    status = service.get_system_status()

    by_name = {b.name: b for b in status.backends}
    assert by_name["Alpaca"].reachable is False
    assert by_name["yfinance"].reachable is True
