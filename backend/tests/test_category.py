"""Unit tests for the pure quoteType -> AssetCategory mapping."""

from __future__ import annotations

import pytest

from cadence.assets.category import (
    AssetCategory,
    AssetScope,
    categorize,
    scope_categories,
)


@pytest.mark.parametrize(
    ("quote_type", "expected"),
    [
        ("EQUITY", AssetCategory.STOCK),
        ("CRYPTOCURRENCY", AssetCategory.CRYPTO),
        ("ETF", AssetCategory.ETF),
        ("MUTUALFUND", AssetCategory.FUND),
    ],
)
def test_known_quote_types_map(quote_type: str, expected: AssetCategory) -> None:
    assert categorize(quote_type) is expected


@pytest.mark.parametrize(
    ("quote_type", "expected"),
    [
        ("equity", AssetCategory.STOCK),
        ("cryptocurrency", AssetCategory.CRYPTO),
        ("Etf", AssetCategory.ETF),
        ("MutualFund", AssetCategory.FUND),
    ],
)
def test_mapping_is_case_insensitive(
    quote_type: str, expected: AssetCategory
) -> None:
    assert categorize(quote_type) is expected


@pytest.mark.parametrize("quote_type", ["INDEX", "FUTURE", "OPTION", "", "  ", "weird"])
def test_unrecognized_maps_to_other(quote_type: str) -> None:
    assert categorize(quote_type) is AssetCategory.OTHER


def test_none_maps_to_other() -> None:
    assert categorize(None) is AssetCategory.OTHER


def test_category_values_are_the_contract() -> None:
    assert AssetCategory.STOCK.value == "stock"
    assert AssetCategory.CRYPTO.value == "crypto"
    assert AssetCategory.ETF.value == "etf"
    assert AssetCategory.FUND.value == "fund"
    assert AssetCategory.OTHER.value == "other"


# --------------------------------------------------------------------------- #
# Asset scope -> categories
# --------------------------------------------------------------------------- #


def test_scope_values_are_the_contract() -> None:
    assert AssetScope.STOCKS.value == "stocks"
    assert AssetScope.CRYPTO.value == "crypto"
    assert AssetScope.BOTH.value == "both"


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (AssetScope.STOCKS, frozenset({AssetCategory.STOCK})),
        (AssetScope.CRYPTO, frozenset({AssetCategory.CRYPTO})),
        (AssetScope.BOTH, frozenset({AssetCategory.STOCK, AssetCategory.CRYPTO})),
    ],
)
def test_scope_categories_maps_each_scope(
    scope: AssetScope, expected: frozenset[AssetCategory]
) -> None:
    assert scope_categories(scope) == expected


def test_scope_categories_accepts_string_value() -> None:
    # A persisted ``session_metadata`` string round-trips to the same set.
    assert scope_categories("crypto") == frozenset({AssetCategory.CRYPTO})


def test_scope_categories_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        scope_categories("commodities")
