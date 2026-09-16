"""Push-notification abstraction.

The rest of the app depends only on the :class:`Notifier` protocol; concrete
delivery lives in :class:`PushoverNotifier`, and :class:`NullNotifier` is a no-op.
:func:`get_notifier` selects between them from :data:`cadence.config.settings`,
mirroring how the broker domain chooses a real client vs. an offline stub.
"""

from __future__ import annotations

from cadence.config import settings
from cadence.notify.base import Notifier
from cadence.notify.null import NullNotifier
from cadence.notify.pushover import PushoverNotifier

__all__ = [
    "Notifier",
    "NullNotifier",
    "PushoverNotifier",
    "get_notifier",
]


def get_notifier() -> Notifier:
    """Provide the notifier. Overridden with a fake in tests.

    Returns a :class:`PushoverNotifier` when both Pushover credentials are
    configured; otherwise a :class:`NullNotifier` so notifications are silently
    disabled and the app still runs normally.
    """
    if settings.PUSHOVER_USER and settings.PUSHOVER_TOKEN:
        return PushoverNotifier()
    return NullNotifier()
