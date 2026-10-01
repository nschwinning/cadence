"""Constants for price-history ingestion."""

from __future__ import annotations

# Lookback window (in days) the daily ingestion pass fetches, large enough to
# backfill a missed day or a weekend/holiday gap while staying small. Dates
# already stored are upserted idempotently.
DAILY_INGEST_LOOKBACK_DAYS = 7
