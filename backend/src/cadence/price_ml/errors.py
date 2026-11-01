"""Exceptions for the price-ML capability."""

from __future__ import annotations


class PriceMlError(Exception):
    """Base class for price-ML errors."""


class InsufficientHistoryError(PriceMlError):
    """An asset lacks the minimum bars required to assemble features."""


class ModelNotTrainedError(PriceMlError):
    """Inference was attempted with no trained model available."""
