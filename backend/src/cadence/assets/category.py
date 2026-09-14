"""Asset category enum and provider ``quoteType`` classification.

Pure mapping logic with no I/O, so every branch is trivially unit-testable.
The category is stored as the enum's string value (see the model) rather than a
native PG enum, keeping migrations simple and extension cheap.
"""

from __future__ import annotations

from enum import StrEnum


class AssetCategory(StrEnum):
    """The supported asset categories. Values are part of the API contract."""

    STOCK = "stock"
    CRYPTO = "crypto"
    ETF = "etf"
    FUND = "fund"
    OTHER = "other"


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
