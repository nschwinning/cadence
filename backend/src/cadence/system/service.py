"""Live reachability probes for the application's external backends.

Each backend the app depends on — the Alpaca broker, the web-search provider,
yfinance market data, and the OpenAI model — is probed with the cheapest call
that proves connectivity (and, where applicable, credentials). Every probe is
isolated: it catches all failures and returns a :class:`ProbeResult` with
``reachable=False`` rather than raising, so one unhealthy backend never breaks
the others or the overall report.

Secret hygiene: results carry only booleans and non-secret identifiers (broker
mode, provider name, model id). A probe's ``detail`` is a short *fixed*
classification derived from the error type/text (see :func:`_classify_error`) —
a raw exception message is never interpolated into the report, so a credential
embedded in an error string can never leak out.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cadence.config import settings

if TYPE_CHECKING:
    from cadence.assets.market_data import MarketDataProvider

logger = logging.getLogger(__name__)

#: Query used for the web-search reachability probe. Kept trivial and generic so
#: the call is as cheap as possible; only connectivity is being verified.
_WEB_SEARCH_PROBE_QUERY = "ping"

#: Ticker used for the yfinance reachability probe (a liquid, always-listed ETF).
_YFINANCE_PROBE_TICKER = "SPY"


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of probing a single backend.

    ``reachable`` is ``None`` when no live probe was performed (the backend is
    unconfigured, or the broker is in offline/stub mode); ``True``/``False``
    reflect the live probe. ``detail`` is a short fixed classification, never a
    raw error message.
    """

    name: str
    configured: bool
    identifier: str | None = None
    reachable: bool | None = None
    latency_ms: float | None = None
    detail: str | None = None


@dataclass(frozen=True)
class SystemStatus:
    """Aggregated per-backend status, ready for ``SystemStatusRead`` validation."""

    backends: list[ProbeResult] = field(default_factory=list)


def _classify_error(exc: BaseException) -> str:
    """Map an exception to a short, fixed, secret-free classification string.

    Only the returned constant is ever surfaced; the raw message is inspected
    here solely to pick a bucket and is never passed through, so a credential
    embedded in an error string cannot leak into the report.
    """
    type_name = type(exc).__name__.lower()
    text = str(exc).lower()

    if (
        "authenticat" in type_name
        or "permission" in type_name
        or "unauthor" in text
        or "forbidden" in text
        or " 401" in text
        or " 403" in text
        or "api key" in text
    ):
        return "unauthorized"
    if "notfound" in type_name or "not found" in text or " 404" in text:
        return "not found"
    if "timeout" in type_name or "timed out" in text or "timeout" in text:
        return "timeout"
    if "connection" in type_name or "connect" in text or "unreachable" in text:
        return "unreachable"
    return "error"


def _elapsed_ms(start: float) -> float:
    """Milliseconds elapsed since a :func:`time.perf_counter` ``start``."""
    return round((time.perf_counter() - start) * 1000, 1)


def probe_alpaca() -> ProbeResult:
    """Probe the Alpaca broker via its clock endpoint (cheapest authenticated call).

    In offline/stub mode, report mode ``stub`` and make no network call. When
    credentials are absent, report not-configured without probing. Otherwise
    construct :class:`AlpacaBroker` *inside* this try/except — never via
    ``Depends(get_broker)`` — so a config/transport failure is contained here and
    the app-level ``ConnectionError`` → 503 handler never fires.
    """
    name = "Alpaca"
    if settings.ALPACA_STUB:
        return ProbeResult(name=name, configured=True, identifier="stub", reachable=None)

    identifier = "paper" if settings.ALPACA_PAPER else "live"
    configured = bool(settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY)
    if not configured:
        return ProbeResult(name=name, configured=False, identifier=identifier)

    start = time.perf_counter()
    try:
        from cadence.broker import AlpacaBroker

        AlpacaBroker().get_clock()
    except Exception as exc:  # noqa: BLE001 - probe must never raise
        return ProbeResult(
            name=name,
            configured=True,
            identifier=identifier,
            reachable=False,
            detail=_classify_error(exc),
        )
    return ProbeResult(
        name=name,
        configured=True,
        identifier=identifier,
        reachable=True,
        latency_ms=_elapsed_ms(start),
    )


def probe_web_search() -> ProbeResult:
    """Probe the active web-search provider with a minimal query.

    ``identifier`` is the configured provider; ``configured`` is whether that
    provider's key is present. Serper returns ``{"error": ...}`` rather than
    raising, so a payload carrying ``error`` is treated as unreachable.
    """
    name = "Web search"
    provider = settings.WEB_SEARCH_PROVIDER
    if provider == "serpapi":
        configured = bool(settings.SERP_API_KEY)
    elif provider == "serper":
        configured = bool(settings.SERPER_API_KEY)
    else:
        configured = False

    if not configured:
        return ProbeResult(name=name, configured=False, identifier=provider)

    start = time.perf_counter()
    try:
        from cadence.agents.tools import _search_serpapi, _search_serper

        search = _search_serpapi if provider == "serpapi" else _search_serper
        payload = search(_WEB_SEARCH_PROBE_QUERY)
    except Exception as exc:  # noqa: BLE001 - probe must never raise
        return ProbeResult(
            name=name,
            configured=True,
            identifier=provider,
            reachable=False,
            detail=_classify_error(exc),
        )

    if isinstance(payload, dict) and payload.get("error"):
        return ProbeResult(
            name=name,
            configured=True,
            identifier=provider,
            reachable=False,
            detail="error",
        )
    return ProbeResult(
        name=name,
        configured=True,
        identifier=provider,
        reachable=True,
        latency_ms=_elapsed_ms(start),
    )


def probe_yfinance(provider: MarketDataProvider | None = None) -> ProbeResult:
    """Probe yfinance market data via a single-ticker info fetch.

    Has no credential, so it is always ``configured``; an empty result or raised
    error marks it unreachable. ``provider`` is injectable for tests.
    """
    name = "yfinance"
    if provider is None:
        from cadence.assets.market_data import YFinanceMarketDataProvider

        provider = YFinanceMarketDataProvider()

    start = time.perf_counter()
    try:
        provider.fetch_info(_YFINANCE_PROBE_TICKER)
    except Exception as exc:  # noqa: BLE001 - probe must never raise
        return ProbeResult(
            name=name,
            configured=True,
            identifier="yfinance",
            reachable=False,
            detail=_classify_error(exc),
        )
    return ProbeResult(
        name=name,
        configured=True,
        identifier="yfinance",
        reachable=True,
        latency_ms=_elapsed_ms(start),
    )


def _build_openai_client() -> object:
    """Construct an OpenAI client. Indirection seam so tests can monkeypatch it."""
    from openai import OpenAI

    return OpenAI(api_key=settings.OPENAI_API_KEY)


def probe_openai() -> ProbeResult:
    """Probe OpenAI via ``models.retrieve(model)``.

    This validates both the key and the configured model id without paying for a
    completion. ``identifier`` is the configured model; when the key is absent the
    backend is reported not-configured with no reachability result.
    """
    name = "OpenAI"
    model = settings.AI_PORTFOLIO_MODEL
    configured = bool(settings.OPENAI_API_KEY)
    if not configured:
        return ProbeResult(name=name, configured=False, identifier=model)

    start = time.perf_counter()
    try:
        client = _build_openai_client()
        client.models.retrieve(model)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - probe must never raise
        return ProbeResult(
            name=name,
            configured=True,
            identifier=model,
            reachable=False,
            detail=_classify_error(exc),
        )
    return ProbeResult(
        name=name,
        configured=True,
        identifier=model,
        reachable=True,
        latency_ms=_elapsed_ms(start),
    )


#: Ordered probe registry: (stable backend name, probe callable). The name is
#: reused when building a timeout/error fallback for a probe that never returned.
_PROBES: tuple[tuple[str, Callable[[], ProbeResult]], ...] = (
    ("Alpaca", probe_alpaca),
    ("Web search", probe_web_search),
    ("yfinance", probe_yfinance),
    ("OpenAI", probe_openai),
)


def get_system_status() -> SystemStatus:
    """Run every backend probe concurrently and aggregate the results.

    Probes run on a thread pool (the stack is sync) and each is bounded by
    ``SYSTEM_STATUS_PROBE_TIMEOUT_SECONDS``. A probe that exceeds the shared
    deadline is reported unreachable with a ``timeout`` detail; the executor is
    shut down without waiting so a hung probe cannot delay the response (its
    thread drains in the background under the underlying client's own timeout).
    Results are returned in the registry's stable order.
    """
    timeout = settings.SYSTEM_STATUS_PROBE_TIMEOUT_SECONDS
    executor = ThreadPoolExecutor(max_workers=len(_PROBES))
    try:
        futures = [(name, executor.submit(fn)) for name, fn in _PROBES]
        deadline = time.monotonic() + timeout
        backends: list[ProbeResult] = []
        for name, future in futures:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                backends.append(future.result(timeout=remaining))
            except FuturesTimeoutError:
                backends.append(
                    ProbeResult(
                        name=name,
                        configured=True,
                        reachable=False,
                        detail="timeout",
                    )
                )
            except Exception as exc:
                logger.warning("System-status probe %s raised", name, exc_info=exc)
                backends.append(
                    ProbeResult(
                        name=name,
                        configured=True,
                        reachable=False,
                        detail=_classify_error(exc),
                    )
                )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return SystemStatus(backends=backends)
