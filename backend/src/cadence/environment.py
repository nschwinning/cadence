"""Deployment environment identity and the trading guard.

Each deployment has a name (``CADENCE_ENVIRONMENT``, e.g. ``QA`` / ``PRD``) and an
Alpaca account behind it. The configured mode (``ALPACA_PAPER``) is not trusted on its
own: the account mode is verified with a read-only broker probe, and orders are refused
when the two disagree, or when the verified account is live and ``ALPACA_ALLOW_LIVE`` is
not set. Reads, valuation and snapshots are unaffected — only order submission is
guarded (by :class:`cadence.orders.gateway.OrderGateway`, the single order path).

Probe results for real Alpaca credentials are cached per process (unknown results only
briefly) so the guard does not call the broker on every order. Brokers without a probe
(test doubles) report ``unknown``, which never blocks.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from cadence.broker.alpaca import AlpacaBroker
from cadence.broker.base import Broker, OrderError
from cadence.broker.models import AccountMode
from cadence.config import settings

#: Seconds a verified (paper / live) probe result is reused.
CACHE_SECONDS = 300.0
#: Seconds an ``unknown`` result is reused, so recovery shows up quickly.
UNKNOWN_CACHE_SECONDS = 30.0

_cache: dict[str, tuple[float, AccountMode]] = {}
_lock = threading.Lock()


class TradingDisabledError(OrderError):
    """An order was refused because this deployment may not trade its account."""


@dataclass(frozen=True)
class EnvironmentStatus:
    """What this deployment is and whether it may trade."""

    environment: str
    configured_mode: AccountMode
    account_mode: AccountMode
    mismatch: bool
    trading_enabled: bool
    reason: str | None


def configured_mode() -> AccountMode:
    """The account mode the configuration asks for."""
    return "paper" if settings.ALPACA_PAPER else "live"


def account_mode(broker: Broker | None) -> AccountMode:
    """The verified account mode behind ``broker`` (cached for real Alpaca brokers)."""
    if broker is None:
        return "unknown"
    probe = getattr(broker, "probe_account_mode", None)
    if probe is None:
        return "unknown"
    if not isinstance(broker, AlpacaBroker):
        mode: AccountMode = probe()
        return mode
    key = broker.credentials_fingerprint
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]
    mode = probe()
    ttl = UNKNOWN_CACHE_SECONDS if mode == "unknown" else CACHE_SECONDS
    with _lock:
        _cache[key] = (now + ttl, mode)
    return mode


def reset_cache() -> None:
    """Forget cached probe results (tests, or after a configuration change)."""
    with _lock:
        _cache.clear()


def resolve_environment(broker: Broker | None) -> EnvironmentStatus:
    """This deployment's identity, verified account mode and trading permission."""
    configured = configured_mode()
    verified = account_mode(broker)
    mismatch = verified != "unknown" and verified != configured
    reason: str | None = None
    if mismatch:
        reason = (
            f"The credentials belong to a {verified} account but ALPACA_PAPER is set for "
            f"{configured}; fix the configuration before trading."
        )
    elif verified == "live" and not settings.ALPACA_ALLOW_LIVE:
        reason = "Live account: set ALPACA_ALLOW_LIVE=true to allow trading real money."
    return EnvironmentStatus(
        environment=settings.CADENCE_ENVIRONMENT,
        configured_mode=configured,
        account_mode=verified,
        mismatch=mismatch,
        trading_enabled=reason is None,
        reason=reason,
    )


def ensure_trading_allowed(broker: Broker) -> None:
    """Raise :class:`TradingDisabledError` when this deployment may not trade."""
    status = resolve_environment(broker)
    if not status.trading_enabled:
        raise TradingDisabledError(f"Trading disabled: {status.reason}")
