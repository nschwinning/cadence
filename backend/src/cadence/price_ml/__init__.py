"""Learned price-direction signal for the AI paper-trading stack.

A single pooled gradient-boosted classifier predicts the direction of each
asset's forward ~21-trading-day return from engineered price features (lagged
price-history returns plus indicators derived from the stored daily closes),
validated with a purged/embargoed walk-forward so the stored confidence is
honest. Signals are precomputed on the nightly cron (one row per asset) and read
by the rebalance flow, degrading to an explicit "unavailable" marker rather than
ever fabricating a signal or failing a run.
"""
