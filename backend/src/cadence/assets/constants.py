"""Eligibility thresholds and evaluation windows for the assets domain.

All monetary thresholds are expressed in USD. Thresholds are fixed constants for
v1 (configurable thresholds are out of scope).
"""

from __future__ import annotations

# Minimum latest price (strictly greater than).
MIN_PRICE_USD = 5

# Minimum average daily turnover over the trailing window (at least).
MIN_AVG_DAILY_TURNOVER_USD = 2_000_000

# Minimum market capitalization (strictly greater than).
MIN_MARKET_CAP_USD = 1_000_000_000

# Minimum available price history in years (at least).
MIN_HISTORY_YEARS = 5

# ---------------------------------------------------------------------------- #
# Crypto-specific thresholds
#
# Crypto is evaluated against a different profile than equities (see
# ``evaluation.py``):
#   * Per-unit price is meaningless for crypto — it depends on token supply, not
#     value — so crypto is NOT evaluated on price at all (no crypto price floor).
#   * Crypto is a young asset class, so a shorter minimum history is required.
#   * Market-cap and liquidity floors are raised to reflect the market's higher
#     typical volumes and to filter thinner coins.
# ---------------------------------------------------------------------------- #

# Minimum average daily turnover for crypto over the trailing window (at least).
MIN_CRYPTO_AVG_DAILY_TURNOVER_USD = 10_000_000

# Minimum crypto market capitalization (strictly greater than).
MIN_CRYPTO_MARKET_CAP_USD = 2_000_000_000

# Minimum available crypto price history in years (at least).
MIN_CRYPTO_HISTORY_YEARS = 1

# Trailing window (in trading sessions) over which average daily turnover is
# computed; roughly three calendar months.
TURNOVER_WINDOW_TRADING_DAYS = 63

# Trailing window (in trading sessions) of daily closes shown on the asset
# details price-history chart; roughly two calendar years.
DETAIL_HISTORY_TRADING_DAYS = 504
