"""Pushover-backed :class:`~cadence.notify.base.Notifier`.

Posts to the Pushover messages API using ``requests``. Credentials come from
:data:`cadence.config.settings` (``PUSHOVER_USER`` / ``PUSHOVER_TOKEN``). Delivery
is best-effort: missing credentials, a transport error, or a non-2xx response are
logged and reported as ``False`` — never raised — so a notification can never break
the caller (e.g. a daily rebalance).
"""

from __future__ import annotations

import logging

import requests

from cadence.config import settings

logger = logging.getLogger(__name__)

#: Pushover messages endpoint.
_PUSHOVER_URL = "https://api.pushover.net/1/messages.json"

#: Network timeout (seconds) for a single send. Short so a slow/unreachable
#: Pushover never stalls the calling job.
_TIMEOUT_SECONDS = 10


class PushoverNotifier:
    """Sends notifications via Pushover, reading credentials from settings."""

    def send(self, message: str, *, title: str | None = None) -> bool:
        user = settings.PUSHOVER_USER
        token = settings.PUSHOVER_TOKEN
        if not user or not token:
            logger.warning(
                "Pushover notification skipped: PUSHOVER_USER/PUSHOVER_TOKEN not set"
            )
            return False

        payload = {"user": user, "token": token, "message": message}
        if title:
            payload["title"] = title

        try:
            response = requests.post(
                _PUSHOVER_URL, data=payload, timeout=_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            logger.warning("Pushover notification failed: %s", exc)
            return False

        if not response.ok:
            logger.warning(
                "Pushover notification rejected: %s %s",
                response.status_code,
                response.text,
            )
            return False
        return True
