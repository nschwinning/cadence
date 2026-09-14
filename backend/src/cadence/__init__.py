"""Cadence backend package."""

from cadence._tls import enable_os_trust_store

__version__ = "0.1.0"

# Trust the OS certificate store before any HTTPS client is constructed, so
# corporate TLS-inspection CAs (e.g. Zscaler) are honoured on managed machines.
enable_os_trust_store()
