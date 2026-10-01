"""Stored daily close prices per asset and per-asset market returns.

A focused time-series store: one ``price_history`` row per asset and trading
date (unique on ``(asset_id, date)``), holding that day's close. History is
backfilled when an asset is added and appended daily by the rebalance cron, so
the Dashboard can report best/worst universe performers over horizons (up to
``1Y`` and ``Max``) that on-demand market-data fetching cannot serve. Returns
are close-to-close price returns (dividends excluded); each asset uses only its
own stored dates, so crypto (24/7) and equity (market-hours) calendars coexist
without fabricated points.
"""
