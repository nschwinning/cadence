"""Notifier protocol: the app depends only on this abstraction.

Concrete delivery (Pushover, or a no-op) lives in sibling modules and is selected
by :func:`cadence.notify.get_notifier`. Sending is best-effort by contract:
:meth:`Notifier.send` never raises — it returns whether delivery was attempted and
accepted — so callers can fire notifications without guarding every call site.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    """Sends a short push notification. Implementations MUST NOT raise."""

    def send(self, message: str, *, title: str | None = None) -> bool:
        """Deliver ``message`` (optionally titled). Return True on accepted delivery.

        Returns False when delivery is skipped (not configured) or fails; the
        condition is logged by the implementation, never raised.
        """
        ...
