"""Domain errors for the assets capability.

These decouple the service/router from provider-specific failures. The router
maps each to a distinct HTTP status code.
"""

from __future__ import annotations


class AssetError(Exception):
    """Base class for all assets-domain errors."""


class UnknownTickerError(AssetError):
    """The provider returned no usable data for the requested ticker."""


class MarketDataUnavailableError(AssetError):
    """The provider or an FX conversion was unavailable (transient failure)."""


class DuplicateAssetError(AssetError):
    """An asset with the same ticker already exists in the universe."""


class UnsupportedCategoryError(AssetError):
    """The instrument's category is not tradeable (only stock and crypto are)."""


class AssetNotFoundError(AssetError):
    """No asset with the requested ticker exists in the stored universe."""
