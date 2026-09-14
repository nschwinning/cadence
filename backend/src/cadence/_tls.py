"""Route TLS verification through the operating system's trust store.

Corporate networks that inspect TLS (e.g. Zscaler) present certificates signed
by a private root CA that lives in the OS trust store but not in ``certifi`` —
which is what ``httpx``/``openai``/``requests`` verify against by default. That
makes outbound HTTPS from the recommender agent fail with
``CERTIFICATE_VERIFY_FAILED``, surfaced by the OpenAI SDK as the generic
"Connection error.".

``truststore`` makes the stdlib ``ssl`` module verify against the OS trust
store, which already trusts the inspection CA on a managed machine. Off such a
network it is a harmless no-op: the OS store holds the same public roots as
certifi, so this is safe to run everywhere (dev laptop, CI, server).
"""

from __future__ import annotations


def enable_os_trust_store() -> None:
    """Make ``ssl`` verify against the OS trust store, before any client is built.

    Best-effort: if ``truststore`` is not installed, leave the default certifi
    behaviour in place rather than break startup.
    """
    try:
        import truststore
    except ModuleNotFoundError:
        return
    truststore.inject_into_ssl()
