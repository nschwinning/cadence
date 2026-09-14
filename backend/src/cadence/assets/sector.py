"""Economic sector enum and provider ``sectorKey`` classification.

Pure mapping logic with no I/O, so every branch is trivially unit-testable.
Parallels :mod:`cadence.assets.category`: the sector is stored as the enum's
string value (the provider's stable slug), not a native PG enum. Unlike
category, sector is optional — a missing or unrecognized provider sector maps
to ``None`` rather than a synthetic ``other`` bucket, because a fabricated
sector would pollute the very filter/benchmark grouping this attribute exists
to enable.
"""

from __future__ import annotations

from enum import StrEnum


class Sector(StrEnum):
    """The supported economic sectors. Values are the provider's stable slugs
    (``sectorKey``) and are part of the API contract.
    """

    TECHNOLOGY = "technology"
    FINANCIAL_SERVICES = "financial-services"
    HEALTHCARE = "healthcare"
    CONSUMER_CYCLICAL = "consumer-cyclical"
    CONSUMER_DEFENSIVE = "consumer-defensive"
    INDUSTRIALS = "industrials"
    ENERGY = "energy"
    BASIC_MATERIALS = "basic-materials"
    REAL_ESTATE = "real-estate"
    UTILITIES = "utilities"
    COMMUNICATION_SERVICES = "communication-services"


# Provider ``sectorKey`` slug (lower-cased) -> Sector. Anything absent yields None.
_SLUG_TO_SECTOR: dict[str, Sector] = {member.value: member for member in Sector}


def classify_sector(sector_key: str | None) -> Sector | None:
    """Classify a provider ``sectorKey`` slug into a :class:`Sector`.

    The match is case-insensitive. A missing/``None``, blank, or unrecognized
    slug returns ``None`` — "no sector" is a first-class state (there is no
    ``OTHER`` fallback), reliably populated only for equities.
    """
    if not sector_key:
        return None
    return _SLUG_TO_SECTOR.get(sector_key.strip().lower())
