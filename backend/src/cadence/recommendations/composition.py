"""The universe-composition value object shared by the dashboard and recommender.

A point-in-time summary of how the asset universe is distributed across sectors
and countries. The dashboard produces it and the recommender renders it into the
agent prompt to steer runs toward under-represented buckets.

Kept dependency-light on purpose — only the fixed :class:`Sector` set — so the
dashboard request path can build it without importing the agent SDK that lives in
:mod:`cadence.recommendations.agent`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompositionEntry:
    """One bucket of a composition breakdown: a display key and its asset count."""

    key: str
    count: int


@dataclass(frozen=True)
class UniverseComposition:
    """A snapshot of the universe's sector and country distribution.

    ``sectors`` covers every economic sector — including those with a zero count,
    so absent sectors are visible to the agent — plus the "no sector" bucket when
    any asset lacks one. ``countries`` lists only the countries present (with the
    "unknown" bucket for assets missing a country), since countries are not drawn
    from a fixed set. Both are ordered by descending count, then key.
    """

    total: int
    sectors: tuple[CompositionEntry, ...]
    countries: tuple[CompositionEntry, ...]

    @property
    def is_empty(self) -> bool:
        """Whether the universe currently contains no assets."""
        return self.total == 0


def empty_composition() -> UniverseComposition:
    """Return an empty composition (no assets).

    Used as the recommender's composition source until the dashboard capability
    lands and can supply the real universe snapshot.
    """
    return UniverseComposition(total=0, sectors=(), countries=())
