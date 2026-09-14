"""Domain errors for the asset-recommendations capability."""

from __future__ import annotations


class RecommendationError(Exception):
    """Base class for all recommendation-domain errors."""


class RecommendationValidationError(RecommendationError):
    """The requested run parameters are invalid (bad count or categories)."""


class RunNotFoundError(RecommendationError):
    """No recommendation run with the requested id exists."""
