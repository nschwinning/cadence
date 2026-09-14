"""Tests for the pure broker symbol-format translation helpers."""

from __future__ import annotations

import pytest

from cadence.broker.models import AssetClass
from cadence.broker.symbols import to_alpaca_symbol, to_canonical_symbol


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("BTC-USD", "BTC/USD"),
        ("btc-usd", "BTC/USD"),
        ("ETH-USDT", "ETH/USDT"),
        ("BTC/USD", "BTC/USD"),  # already Alpaca form is left as-is
        ("BTCUSD", "BTC/USD"),  # joined form with a known fiat suffix
        ("ETHUSDT", "ETH/USDT"),
    ],
)
def test_to_alpaca_symbol_crypto(ticker: str, expected: str) -> None:
    assert to_alpaca_symbol(ticker, AssetClass.CRYPTO) == expected


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("BTC/USD", "BTC-USD"),
        ("btc/usd", "BTC-USD"),
        ("ETH/USDT", "ETH-USDT"),
        ("BTC-USD", "BTC-USD"),  # already canonical is left as-is
    ],
)
def test_to_canonical_symbol_crypto(symbol: str, expected: str) -> None:
    assert to_canonical_symbol(symbol, AssetClass.CRYPTO) == expected


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "brk.b"])
def test_equity_passthrough_uppercased(ticker: str) -> None:
    up = ticker.upper()
    assert to_alpaca_symbol(ticker, AssetClass.EQUITY) == up
    assert to_canonical_symbol(ticker, AssetClass.EQUITY) == up


@pytest.mark.parametrize("canonical", ["BTC-USD", "ETH-USDT", "SOL-EUR"])
def test_crypto_round_trip(canonical: str) -> None:
    alpaca = to_alpaca_symbol(canonical, AssetClass.CRYPTO)
    assert to_canonical_symbol(alpaca, AssetClass.CRYPTO) == canonical


def test_equity_round_trip() -> None:
    assert (
        to_canonical_symbol(
            to_alpaca_symbol("AAPL", AssetClass.EQUITY), AssetClass.EQUITY
        )
        == "AAPL"
    )
