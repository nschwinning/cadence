"""Unit tests for the pure sectorKey -> Sector mapping."""

from __future__ import annotations

import pytest

from cadence.assets.sector import Sector, classify_sector


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("technology", Sector.TECHNOLOGY),
        ("financial-services", Sector.FINANCIAL_SERVICES),
        ("healthcare", Sector.HEALTHCARE),
        ("consumer-cyclical", Sector.CONSUMER_CYCLICAL),
        ("consumer-defensive", Sector.CONSUMER_DEFENSIVE),
        ("industrials", Sector.INDUSTRIALS),
        ("energy", Sector.ENERGY),
        ("basic-materials", Sector.BASIC_MATERIALS),
        ("real-estate", Sector.REAL_ESTATE),
        ("utilities", Sector.UTILITIES),
        ("communication-services", Sector.COMMUNICATION_SERVICES),
    ],
)
def test_known_slugs_map(slug: str, expected: Sector) -> None:
    assert classify_sector(slug) is expected


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("Technology", Sector.TECHNOLOGY),
        ("FINANCIAL-SERVICES", Sector.FINANCIAL_SERVICES),
        ("  real-estate  ", Sector.REAL_ESTATE),
    ],
)
def test_mapping_is_case_insensitive_and_trimmed(
    slug: str, expected: Sector
) -> None:
    assert classify_sector(slug) is expected


@pytest.mark.parametrize("slug", ["", "  ", "conglomerates", "weird", "stock"])
def test_unknown_or_blank_maps_to_none(slug: str) -> None:
    assert classify_sector(slug) is None


def test_none_maps_to_none() -> None:
    assert classify_sector(None) is None


def test_sector_values_are_the_contract() -> None:
    assert Sector.TECHNOLOGY.value == "technology"
    assert Sector.FINANCIAL_SERVICES.value == "financial-services"
    assert Sector.COMMUNICATION_SERVICES.value == "communication-services"
