"""No-op :class:`~cadence.notify.base.Notifier`.

Used when push credentials are not configured, so notification call sites stay
unconditional while delivery is silently disabled.
"""

from __future__ import annotations


class NullNotifier:
    """A notifier that does nothing and reports no delivery."""

    def send(self, message: str, *, title: str | None = None) -> bool:
        return False
