"""Deterministic, rule-based strategy-bot subsystem.

A parallel domain to AI paper trading: each bot runs one pure technical strategy
(v1: MA Crossover) over a single universe asset, long-only, all-in on a whole-share
position, driven by a cron-triggered intraday ``/tick``. The subsystem owns its own
persistence (:mod:`.models`), strategy layer (:mod:`.strategy` + :mod:`.registry`),
risk/execution engine (:mod:`.engine`), intraday market-data seam
(:mod:`.market_data`), and service/runner (:mod:`.service`).

It touches the rest of the app at exactly two read seams: the shared asset universe
(input) and the dashboard comparison contract (output, via
:func:`.service.dashboard_performance`). Neither subsystem imports the other.
"""

from __future__ import annotations
