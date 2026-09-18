## Why

Paper-trading sessions are labeled by `strategy_key`, which is the same (`ai_buy_hold`) for every AI portfolio, so sessions are indistinguishable in the list and detail views. Surfacing the portfolio name does not fix this on its own: the AI generates generic, colliding names (e.g. every build is "AI Growth"). The system needs portfolio names that are actually distinct, then it needs to show them.

## What Changes

- At AI-portfolio build time, the system generates a **distinct, human-friendly portfolio name** (Docker-style: risk profile + adjective + a scientist/investor surname, e.g. "Aggressive Jolly Wozniak"), guaranteed unique against existing portfolio names, instead of using the AI's generic name. This mirrors the sibling trading-bot app's `name_generator`.
- The paper-trading session read model gains the traded portfolio's `name` so any client can label a session by its portfolio.
- The paper-trading **sessions list** and **session detail header** identify each session by its portfolio name as the primary label, with the strategy shown as secondary context. A session whose portfolio name cannot be resolved falls back to the strategy label.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `ai-paper-trading`: the "Build an AI portfolio and execute it as paper trades" requirement is extended so the portfolio created by a build is given a generated, distinct name; the "Read paper-trading session data" requirement is extended so a session returned to a client includes its portfolio's name.
- `app-shell`: the "Portfolio and paper-trading views" requirement is extended so the session list and detail identify each session by its portfolio name rather than its strategy key.

## Impact

- **Backend:** new `name_generator` utility (adjective + famous-name word lists + `generate_unique_name`, ported from trading-bot); `ai_portfolio/service.py` build path uses it (checking existing portfolio names) in place of `result.portfolio_name`; `portfolios/service.py` gains a helper to fetch existing names; `PaperTradingSessionRead` schema gains `portfolio_name`; `PaperTradingSession` model gains a view-only accessor to `Portfolio.name`. No Alembic migration (naming happens at create time; the read surface is derived).
- **Frontend:** `PaperTradingSession` type, `PaperTradingPage` list label + column header, `PaperTradingSessionPage` header. Co-located Vitest updates.
- **No breaking changes:** the read field is additive and `strategy_key` remains in the payload and UI. Existing portfolios keep their current names; only new builds get generated names.
