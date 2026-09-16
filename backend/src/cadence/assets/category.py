"""Asset category enum and provider ``quoteType`` classification.

Pure mapping logic with no I/O, so every branch is trivially unit-testable.
The category is stored as the enum's string value (see the model) rather than a
native PG enum, keeping migrations simple and extension cheap.
"""

from __future__ import annotations

from enum import StrEnum


class AssetCategory(StrEnum):
    """All asset categories the classifier can produce. Values are part of the
    API contract.

    Only :data:`SUPPORTED_CATEGORIES` are tradeable and may enter the universe;
    the remaining members exist so :func:`categorize` can *detect* and reject
    unsupported instruments, and so any pre-existing rows still read.
    """

    STOCK = "stock"
    CRYPTO = "crypto"
    ETF = "etf"
    FUND = "fund"
    OTHER = "other"


#: Tradeable categories Cadence supports. The AI allocates across the ENTIRE
#: universe and trades it on Alpaca, so only categories Alpaca can trade —
#: stocks and crypto — are allowed to enter the universe. Anything else is
#: rejected at add time rather than producing failed orders later.
SUPPORTED_CATEGORIES: frozenset[AssetCategory] = frozenset(
    {AssetCategory.STOCK, AssetCategory.CRYPTO}
)


class AssetScope(StrEnum):
    """Which supported asset categories an AI-managed portfolio may hold.

    Chosen at build time and persisted on the session, so daily rebalances honour
    it. Values are part of the API contract (the build request's ``asset_types``).
    ``BOTH`` is the default and preserves the original whole-universe behaviour.
    """

    STOCKS = "stocks"
    CRYPTO = "crypto"
    BOTH = "both"


#: Asset scope -> the concrete supported categories it admits.
_SCOPE_TO_CATEGORIES: dict[AssetScope, frozenset[AssetCategory]] = {
    AssetScope.STOCKS: frozenset({AssetCategory.STOCK}),
    AssetScope.CRYPTO: frozenset({AssetCategory.CRYPTO}),
    AssetScope.BOTH: SUPPORTED_CATEGORIES,
}


def scope_categories(scope: AssetScope | str) -> frozenset[AssetCategory]:
    """Map an :class:`AssetScope` (or its string value) to the categories it admits.

    Pure lookup with no I/O. A plain string is coerced to :class:`AssetScope`,
    so a persisted ``session_metadata`` value round-trips; an unrecognized value
    raises :class:`ValueError` (via the enum), surfacing bad data loudly.
    """
    return _SCOPE_TO_CATEGORIES[AssetScope(scope)]


# Provider ``quoteType`` (upper-cased) -> category. Anything absent maps to OTHER.
_QUOTE_TYPE_TO_CATEGORY: dict[str, AssetCategory] = {
    "EQUITY": AssetCategory.STOCK,
    "CRYPTOCURRENCY": AssetCategory.CRYPTO,
    "ETF": AssetCategory.ETF,
    "MUTUALFUND": AssetCategory.FUND,
}


def categorize(quote_type: str | None) -> AssetCategory:
    """Classify a provider ``quoteType`` into an :class:`AssetCategory`.

    The match is case-insensitive. A missing/``None`` or unrecognized instrument
    type falls back to :attr:`AssetCategory.OTHER`.
    """
    if not quote_type:
        return AssetCategory.OTHER
    return _QUOTE_TYPE_TO_CATEGORY.get(quote_type.upper(), AssetCategory.OTHER)
