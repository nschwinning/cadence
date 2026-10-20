## Why

Users curate a small **watchlist** of emerging, tracked-but-not-traded candidate assets (via watchlist-targeted recommendation runs). Today the AI portfolio build and daily rebalance only ever consider `universe`-membership assets — the candidate pool is queried with the default `membership = universe` filter — so a watchlist asset can never be picked by the AI, no matter how a user curates it. This change lets a user opt a new portfolio into **also** considering its watchlist assets, turning the watchlist into an actionable staging area rather than a passive tracker.

## What Changes

- The AI portfolio build request gains a new per-session opt-in, **`include_watchlist`** (default **off**). It is chosen at build time and **frozen on the session** for its lifetime — the same build-time-frozen pattern as `use_fundamentals`, the technical-indicator opt-in, learning feedback, stop-loss, and risk guardrails.
- When a session opted in, the candidate universe assembled for the AI is the **union of `universe`-membership and `watchlist`-membership assets**. When off (the default, and for sessions built before this option), the candidate universe stays `universe`-only — today's behavior, unchanged.
- The opt-in governs both the **opening allocation** (which runs through an initial rebalance) and **every subsequent daily rebalance**. Watchlist candidates are subject to the **same** downstream treatment as universe candidates: the session's asset scope, stop-loss quarantine, the trend gate (when opted in), eligibility, and the unexecutable-ticker exclusion.
- The session read payload reports the frozen `include_watchlist` setting; the AI build form gains an **"Include watchlist assets"** toggle (default off); the session detail view shows the frozen setting as a fact tile.

## Capabilities

### Modified Capabilities

- `ai-paper-trading`: the build request accepts and freezes the `include_watchlist` opt-in (new per-session frozen option), and the session read payload reports it.
- `daily-rebalancing`: when a session opted in, the rebalance candidate universe is assembled from both `universe` and `watchlist` membership (union), still restricted to the session's asset scope and subject to the existing quarantine and trend gates; when not opted in, it stays `universe`-only.
- `app-shell`: the AI build form gains an "Include watchlist assets" toggle (default off) sent with the build request, and the session detail view displays the frozen watchlist-inclusion setting.

## Impact

- **Backend**: new frozen boolean column `paper_trading_sessions.include_watchlist` (+ Alembic migration chaining from head `a1c3e5f7b9d2`); `create_session`, `AIBuildParams` (field + `to_payload`/`from_payload`), the build flow, `AIPortfolioBuildRequest`, the build router mapping, and `PaperTradingSessionRead` all thread the flag; the rebalance flow (`ai_portfolio/flows/rebalance.py`) consumes it to broaden the `list_assets` membership filter. No change to `assets` service defaults (callers that omit `membership` still get universe-only).
- **Frontend**: `AIPortfolioBuildRequest` and `PaperTradingSession` types gain the flag; `BuildAIPortfolioCard` gains a toggle + payload field; `PaperTradingSessionPage` gains a read-only fact tile. Session fixtures carrying `use_fundamentals` gain the new flag.
- **Data/compatibility**: additive, default off; existing sessions (NULL/absent) behave exactly as today. No change to how the watchlist is curated.
