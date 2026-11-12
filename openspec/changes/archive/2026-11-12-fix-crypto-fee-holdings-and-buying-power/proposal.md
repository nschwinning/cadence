## Why

Alpaca charges its crypto buy fee **in the coin received**: buying 1,000 ADA delivers roughly
0.25% less ADA. Cadence records the full filled quantity in the AI portfolio's ledger *and*
charges the fee as cash, so every crypto buy leaves the ledger slightly above the account's
holding (and the fee counted twice). On the Admin page this shows as permanent crypto
"shortfalls" (e.g. 2.02 ADA, 0.0226 SOL) that Restore cannot fix — Alpaca rejects crypto orders
under $10 — and a full crypto exit asks to sell more than the account holds, which the long-only
guard (and Alpaca) refuse. Separately, the Admin page and dashboard tile use Alpaca's
`buying_power`, which is **margin** buying power (up to 4× equity intraday), while Cadence never
uses margin — the cash buying power is the relevant ceiling.

## What Changes

- **Crypto buys are booked net of the coin fee**: the ledger records the quantity actually
  received (filled quantity × (1 − crypto fee rate)) at the filled price; the fee stays in the
  session's fees, so the session's cash identity is unchanged and the fee is counted once.
- **Crypto sells never exceed the account's holding**: an AI-portfolio crypto sell is capped at
  what the account holds, so a full exit is never refused over fee dust.
- **$10 minimum for crypto orders**: AI rebalances, Restore and Flatten skip crypto orders worth
  less than $10 with an explicit reason instead of sending orders Alpaca rejects.
- **Write off crypto fee gaps** (Admin): a crypto shortfall of at most 1% of Cadence's quantity
  can be written off — the AI portfolios' ledger quantities are lowered to the account's holding,
  proportionally to their share, at unchanged average cost. No order is sent. This repairs the
  existing gaps (and their double-counted fee).
- **Administrator rejections are closed at once** in the order journal (nothing to book), so they
  never linger as unresolved.
- **Buying power**: the Admin page shows **cash buying power** (Alpaca's non-marginable buying
  power) next to **margin buying power**; the dashboard tile caps free capital at the lower of the
  two and bases its "no buying power" warning on it.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: net-of-fee crypto booking, capped crypto sells, $10 crypto minimum.
- `broker-account-admin`: write-off action; $10 crypto minimum in Restore/Flatten; cash and margin
  buying power in the overview.
- `order-journal`: administrator rejections closed immediately.
- `app-shell`: Admin page write-off action and buying-power figures; dashboard tile capped by
  cash buying power.

## Impact

- Backend: `paper_trading/service.py` (`book_fill` net quantity for crypto buys),
  `ai_portfolio/executor.py` (crypto sell cap via the gateway's holding, `MIN_CRYPTO_NOTIONAL_USD`
  10), `broker/models.py` + `broker/alpaca.py` (`AccountInfo.cash_buying_power` from
  `non_marginable_buying_power`), `admin/service.py` + router + schemas (write-off, minimum,
  buying power), `orders/gateway.py` (admin rejection resolved).
- Frontend: Admin page (Write off action, buying-power figures), `AccountStateTile`, types.
- No migration. Existing ledgers keep their gross quantities until written off.
