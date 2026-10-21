# Tasks

## 1. Frontend — session detail fact tile

- [x] 1.1 In `frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`, add a read-only **Technical indicators** fact tile to the `SessionHeader` `<dl>`, rendering `On` when `session.use_technical_indicators` is true and `Off` otherwise, styled like and grouped with the existing Company fundamentals / Watchlist assets tiles (place it alongside the other strategy opt-in tiles).

## 2. Frontend — tests

- [x] 2.1 In the co-located `PaperTradingSessionPage` test, assert the **Technical indicators** tile renders `On` for a session with `use_technical_indicators: true` and `Off` when false. Update any existing count-based assertions (e.g. `getAllByText('Off')`) to account for the new default-off tile.

## 3. Verify

- [x] 3.1 Frontend gates: `cd frontend && npm run -s typecheck && npx vitest run && npm run build`.
- [x] 3.2 `openspec validate add-session-technical-indicators-tile --strict`.
