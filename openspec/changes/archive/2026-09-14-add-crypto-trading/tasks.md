## 1. Broker: asset class + symbol translation

- [x] 1.1 Add an `AssetClass` string enum (`EQUITY = "equity"`, `CRYPTO = "crypto"`) to `broker/models.py` and an `asset_class: AssetClass = AssetClass.EQUITY` field to `Order`. Verify: `broker.models` imports; `Order()` defaults to equity.
- [x] 1.2 Add `broker/symbols.py` — pure `to_alpaca_symbol(ticker, asset_class)` (crypto `BTC-USD`→`BTC/USD`, equity passthrough), `to_canonical_symbol(symbol, asset_class)` (crypto `BTC/USD`→`BTC-USD`, equity passthrough), tolerant of already-converted input. Verify: unit tests round-trip both formats and leave equities untouched.

## 2. Broker: crypto routing

- [x] 2.1 Update the `Broker` protocol (`broker/base.py`) and both implementations so `get_quote`, `buy`, and `sell` accept an `asset_class: AssetClass = AssetClass.EQUITY` argument. Verify: `StubBroker`/`AlpacaBroker` still satisfy `isinstance(..., Broker)`.
- [x] 2.2 `AlpacaBroker.submit_order`/`buy`/`sell`: translate the symbol to Alpaca format by asset class, and for crypto force `time_in_force="gtc"` and send fractional `qty`. Verify: mocked-session test asserts a crypto buy posts `symbol="BTC/USD"`, `time_in_force="gtc"`, fractional qty; equity order unchanged (`day`).
- [x] 2.3 `AlpacaBroker.get_quote`: for crypto call `GET {DATA}/v1beta3/crypto/us/latest/quotes?symbols=BTC/USD` (fallback `.../latest/trades`), parsing `quotes[sym].bp/ap` / `trades[sym].p`; equity path unchanged. Verify: mocked-session test returns a crypto quote from the crypto endpoint.
- [x] 2.4 `AlpacaBroker._parse_position`: read the payload's `asset_class` and translate crypto symbols back to canonical (`BTC/USD`→`BTC-USD`) so positions reconcile with the universe. Verify: mocked-session test maps a crypto position to a canonical ticker.
- [x] 2.5 `StubBroker`: accept the new `asset_class` args (behavior unchanged) and keep fractional-quantity math working. Verify: existing stub tests pass; a fractional buy/sell updates cash/position.

## 3. Executor: fractional, class-aware sizing

- [x] 3.1 Add a min-notional constant (`MIN_CRYPTO_NOTIONAL_USD = 1.0`) and crypto qty precision. Change `TradeResult.shares` to `float`.
- [x] 3.2 `execute_build`/`execute_rebalance` accept `asset_classes: dict[str, AssetClass]` (default equity) and pass the per-ticker class to `broker.get_quote`/`buy`/`sell`. Equity sizing stays whole-share (skip < 1); crypto sizes fractional units (skip when notional < `MIN_CRYPTO_NOTIONAL_USD`). Verify: unit tests cover a crypto build (fractional shares placed) and a small-notional skip.
- [x] 3.3 `execute_rebalance` uses fractional current/target quantities for crypto (no `int()` truncation) and a notional-based delta threshold; add a `market_open: bool = True` param so that when the equities market is closed, equity tickers are skipped (reason "equity market closed") while crypto still trades. Verify: unit test with `market_open=False` skips equities and trades crypto; crypto deltas buy/sell/exit correctly.

## 4. Service: class map + 24/7 rebalance

- [x] 4.1 Build a `ticker -> AssetClass` map from the universe (crypto iff `Asset.category == CRYPTO`), rebuilt after discovery-adds, and pass it to the executor in both build and rebalance. Verify: a crypto asset in the universe routes as crypto.
- [x] 4.2 Rebalance flow: compute `market_open = broker.is_market_open()`; if closed AND neither held positions nor targets include any crypto, record the skipped run + event as today; otherwise proceed and pass `market_open` to the executor. Positions now key by canonical symbol. Verify: closed-market equity-only session still records skipped; closed-market session holding/targeting crypto trades the crypto.
- [x] 4.3 `ai_portfolio/agent.py` prompt: tell the AI that candidates include crypto (via `category`), that crypto uses yfinance-style tickers (e.g. `BTC-USD`) and trades 24/7, and to weight crypto per its risk. Verify: no behavior regression in the fake-agent tests.

## 5. Assets: crypto is tradable

- [x] 5.1 Confirm a crypto symbol (`BTC-USD`) can be added and is stored with `category == crypto` (yfinance `CRYPTOCURRENCY` → CRYPTO already maps). Ensure eligibility does not hard-block trading (eligibility is informational; the AI trades all universe tickers). Verify: a test adds a crypto asset (fake provider) and it appears in the universe classified as crypto.

## 6. Verification

- [x] 6.1 `uv run pytest` green (new crypto tests included), `uv run ruff check .` clean, `uv run mypy src/cadence` clean.
- [x] 6.2 `uv run alembic check` reports no new operations (code-only change, no migration).
- [x] 6.3 `openspec validate add-crypto-trading --strict` passes.
