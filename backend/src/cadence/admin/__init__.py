"""Broker-account admin capability.

A live view of the one shared Alpaca account every AI portfolio, strategy bot and bot
orchestrator trades in, reconciled against Cadence's own books, plus selling of orphan
positions no Cadence record owns. All logic lives in :mod:`cadence.admin.service`; the
router in :mod:`cadence.api.routers.admin` is a thin shell over it.
"""
