"""System-status capability.

Live, read-only reachability + latency probing of the application's external
backends (Alpaca broker, web-search provider, yfinance market data, OpenAI
model). All probe logic lives in :mod:`cadence.system.service`; a thin router
exposes it at ``GET /api/v1/system/status``.
"""
