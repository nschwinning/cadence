"""Pure symbol-format translation at the brokerage boundary.

The asset universe stores crypto tickers in yfinance/canonical form (``BTC-USD``:
uppercase, dash-separated). Alpaca's trading and market-data APIs use a slash
(``BTC/USD``) and may report positions in that form. These helpers convert
between the two formats and leave equities untouched. They contain no I/O and no
business logic — callers decide the :class:`AssetClass`; nothing here sniffs it.
"""

from __future__ import annotations

from cadence.broker.models import AssetClass

#: Fiat/stablecoin quote currencies we recognize when splitting a joined crypto
#: symbol like ``BTCUSD`` into base/quote. Ordered longest-first so ``USDT`` is
#: matched before ``USD``.
_FIAT_SUFFIXES = ("USDT", "USDC", "USD", "EUR", "GBP", "USDP")


def to_alpaca_symbol(ticker: str, asset_class: AssetClass) -> str:
    """Convert a canonical universe ticker to Alpaca's brokerage format.

    Equities are returned upper-cased and otherwise unchanged. Crypto is
    upper-cased and expressed with a ``/`` separator: ``BTC-USD`` -> ``BTC/USD``.
    Input already in ``BTC/USD`` form is left as-is, and a joined form like
    ``BTCUSD`` (with a known fiat suffix) has the separator inserted.
    """
    symbol = ticker.strip().upper()
    if asset_class != AssetClass.CRYPTO:
        return symbol
    if "/" in symbol:
        return symbol
    if "-" in symbol:
        base, _, quote = symbol.partition("-")
        return f"{base}/{quote}"
    for suffix in _FIAT_SUFFIXES:
        if symbol.endswith(suffix) and len(symbol) > len(suffix):
            base = symbol[: -len(suffix)]
            return f"{base}/{suffix}"
    return symbol


def to_canonical_symbol(symbol: str, asset_class: AssetClass) -> str:
    """Convert a brokerage symbol back to the canonical universe format.

    Equities are returned upper-cased and otherwise unchanged. Crypto is
    upper-cased with the ``/`` separator converted to ``-``: ``BTC/USD`` ->
    ``BTC-USD``. Input already in ``BTC-USD`` form is left as-is.
    """
    normalized = symbol.strip().upper()
    if asset_class != AssetClass.CRYPTO:
        return normalized
    if "/" in normalized:
        base, _, quote = normalized.partition("/")
        return f"{base}-{quote}"
    return normalized
