"""Unit tests for the pure quoteType -> AssetCategory mapping."""

from __future__ import annotations

import pytest

from cadence.assets.category import AssetCategory, categorize


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
