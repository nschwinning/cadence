# Refine universe categories and recommender de-duplication

## Why

Two problems surfaced in use:

1. **Recommender returns duplicates.** The recommender prompt includes the
   universe's sector/country *composition* as a soft diversification steer, but it
   never tells the agent which tickers already exist. So the agent keeps proposing
   names already in the universe; server-side they are caught as
   `skipped_duplicate`, and a run comes back full of duplicates with few or no new
   assets added.

2. **Untradeable categories.** Now that the AI allocates across the ENTIRE universe
   and trades it on Alpaca, every category present WILL be traded. Alpaca trades
   stocks and crypto (and ETFs, which trade like stocks) but not mutual funds, and
   "other" instruments are unpredictable. Per product decision, Cadence supports
   **stocks and crypto only**; any other category should be kept out of the
   universe rather than producing failed orders later.

## What Changes

- **Recommender excludes existing assets.** Pass the current universe's tickers to
  the recommender agent as an explicit exclusion list, and instruct it to never
  propose an asset already present. Server-side dedup remains as a safety net.
- **Restrict supported categories to stock + crypto.** Adding an asset that the
  provider classifies as anything other than stock or crypto is rejected with a
  clear error. The recommender only accepts stock/crypto category requests. The
  frontend offers only stock and crypto wherever a category is chosen or filtered.

## Impact

- Affected specs: `asset-recommendations` (exclude existing), `assets` (supported
  categories restricted to stock + crypto).
- Affected code: `recommendations/agent.py` (prompt + protocol + impl),
  `recommendations/stub.py`, `recommendations/service.py`; `assets/service.py`
  (`add_asset` category gate), `assets/errors.py` (new unsupported-category error),
  `api/routers/assets.py` (error mapping); frontend recommender form + asset
  category filter. Backend + frontend tests.
- No database/schema/migration change (category is already a stored string; the
  enum keeps its members for classification/detection and for reading any existing
  rows).
