## Why

The daily rebalance agent decides what to buy, sell, and hold using only each
asset's ticker, company name, sector, category, and (when trend-gating is on)
technical indicators. It sees no company financials, even though the recently
added quarterly SEC EDGAR refresh now populates `AssetFundamentals` for every
`category=stock` asset. The agent is told to favour "strong long-term
fundamentals" but is handed no fundamentals to reason over. This change closes
that gap by feeding a compact, per-ticker fundamentals block into a new,
versioned rebalance prompt — delivered as a **per-session opt-in (default off)**,
mirroring the project's established pattern for technical indicators, stop-loss,
risk guardrails, and learning feedback.

## What Changes

- Add a new **REBALANCE prompt version (v4)** — the current latest is v3 — seeded
  via an Alembic migration that copies the existing v3 seeding pattern. Its
  instructions document a new per-ticker `fundamentals` object and how to weigh
  it, worded **defensively** ("when present") so a v4 session that did not opt in
  reads cleanly with no fundamentals attached.
- Add a per-session **`use_fundamentals` opt-in flag** (boolean, default **off**),
  frozen onto the session at build time exactly like the other opt-ins. A new
  session's rebalances attach fundamentals only when the flag is on **and** the
  frozen prompt version is `>= FUNDAMENTALS_PROMPT_VERSION`; existing sessions and
  opted-out sessions are byte-for-byte unchanged.
- When the flag is on, attach a `fundamentals` sub-object to **each candidate and
  each current holding** passed to the rebalance agent. The block carries only
  figures derivable from the stored latest-annual (FY/10-K) data with **no extra
  fetches**: gross / operating / net margin, diluted EPS (falling back to basic),
  and revenue / net income / operating cash flow as scale and profitability
  signals.
- Render an explicit **"fundamentals unavailable"** marker for assets without a
  usable fundamentals row (crypto, missing rows, or non-`available` status) so the
  agent never fabricates figures.
- Surface the opt-in end to end: an **AI build-form toggle** (default off), the
  flag on the build request and session read schemas, and a **session-detail fact
  tile** showing whether fundamentals were enabled for the session.
- Eager-load the `Asset.fundamentals` relationship on the universe query to avoid
  N+1 lazy loads when the block is assembled.

Non-goals (explicitly out of scope): the build prompt, the crypto rebalance
prompt, any price-derived ratio (e.g. P/E), multi-period growth, leverage /
balance-sheet metrics, a build-time prompt-version selector, and changing when
fundamentals are refreshed.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: Adds a per-session `use_fundamentals` opt-in (default off)
  that is accepted and frozen at build and surfaced on session reads; when it is
  on and the session is frozen on the fundamentals-aware prompt version, the
  rebalance agent's prompt gains a per-ticker fundamentals block (on candidates
  and holdings) derived from stored fundamentals that degrades gracefully when
  fundamentals are unavailable.
- `app-shell`: The AI build form gains a fundamentals opt-in toggle (default off)
  sent with the build request, and the session-detail view shows the session's
  fundamentals configuration as a fact tile.

## Impact

- **Backend code**: `ai_portfolio/constants.py` (new `FUNDAMENTALS_PROMPT_VERSION`),
  `ai_portfolio/_helpers.py` (attach `fundamentals` to candidates/holdings + a pure
  derivation helper), `ai_portfolio/flows/build.py` and `flows/rebalance.py` (gate
  on the opt-in and frozen version), `ai_portfolio/params.py` (new `use_fundamentals`
  field), `paper_trading/service.py` (`create_session` stores the flag),
  `assets/service.py` (`list_assets` eager-loads `Asset.fundamentals`),
  `api/schemas.py` + `api/routers/ai_portfolio.py` (request + read field and the
  request→params mapping).
- **Database**: a new Alembic migration adding the non-nullable `use_fundamentals`
  boolean column (default/`server_default` false) to `paper_trading_sessions`, and a
  second Alembic migration seeding REBALANCE prompt v4 into the existing
  `rebalance_prompt` table. Downgrades drop the column / delete the seeded row.
- **Frontend**: `BuildAIPortfolioCard.tsx` (opt-in toggle, default off, added to the
  build payload), `types/api.ts` (build request + session read types),
  `PaperTradingSessionPage.tsx` (fundamentals fact tile).
- **Data dependency**: relies on `AssetFundamentals` rows populated by the existing
  quarterly SEC EDGAR refresh; absent/partial data is handled gracefully.
