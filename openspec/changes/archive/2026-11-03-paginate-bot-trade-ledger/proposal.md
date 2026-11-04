## Why

The bot detail page's trade ledger is unbounded. `GET /api/v1/bots/sessions/{id}/trades`
(`api/routers/bots.py` `list_bot_trades`) loads a session's **entire** `trades`
relationship into memory, sorts it, and returns every row; `BotSessionPage.tsx`
then renders the whole list. A strategy bot ticks every five minutes during market
hours and can accumulate many trades, so a long-running session makes the request
and the table grow without limit — slow to load and awkward to read. The ledger
needs server-side pagination.

## What Changes

- The trades endpoint accepts `limit`/`offset` query parameters (default page size
  20, max 100) and returns a single bounded page ordered most-recent-first, plus the
  full `total` count so the client can show how many pages exist. Invalid parameters
  return `422`; an unknown session still returns `404`.
- The service gains a paginated trade query that orders by `created_at` descending
  with `LIMIT`/`OFFSET` and counts the total separately, instead of loading the whole
  `trades` relationship.
- The bot detail page gains pagination controls (previous/next with a page indicator)
  that fetch one page at a time, keeping most-recent-first ordering and the existing
  empty state.

No change to trade storage, the value-history chart, KPIs, the tick/snapshot jobs, or
notifications.

## Capabilities

### Modified Capabilities
- `strategy-bots`: the trade-ledger read API becomes paginated (bounded page + total
  count) rather than returning the entire ledger.

## Impact

- Backend: `api/routers/bots.py` (`list_bot_trades` gains `limit`/`offset`),
  `strategy_bots/service.py` (new paginated trade query + count), `api/schemas.py`
  (response already `{items,total}`; unchanged shape).
- Frontend: `pages/bots/BotSessionPage.tsx` (pagination controls + page state),
  `api/` trades fetch gains page params.
- No migration, no schema/column change, no new dependency.
