"""Technical-indicator compute, storage, and nightly precompute for Cadence.

A focused port of quantara's pure-pandas indicator engine, restricted to a
close+volume subset. The engine computes a fixed set of indicators from an
asset's daily price history, derives a deterministic uptrend **gate** used to
hard-filter new entries, and a small set of **reversal flags** handed to the AI
for held-position exit decisions. Results are stored as the latest snapshot per
asset (one row) with a run-audit record.
"""
