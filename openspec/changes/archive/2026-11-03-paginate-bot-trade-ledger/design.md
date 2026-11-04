## Context

`list_bot_trades` loads `row.trades` (the full relationship), sorts it in Python, and
returns every row as `BotTradeListResponse{items, total}`. The frontend renders the
entire list. This design keeps the response shape and introduces offset-based paging
end to end.

## Goals

- Serve one bounded page of trades per request without materialising the whole ledger.
- Preserve the `{items, total}` response shape and most-recent-first ordering.
- Give the detail page simple prev/next navigation with a page indicator.

## Decisions

### Offset-based paging over cursor paging

Use `limit`/`offset` query parameters. The ledger is append-only and the UI needs a
page count and prev/next, which offset paging serves directly. Cursor paging would add
complexity (opaque tokens) for no benefit at this scale. Default `limit = 20`,
maximum `limit = 100`, `offset >= 0`; FastAPI `Query(..., ge=…, le=…)` enforces the
bounds and yields `422` automatically on violation.

### Separate count query for `total`

`total` stays the **full** trade count (not the page length) so the client can compute
page count. The service issues two queries: a `SELECT ... ORDER BY created_at DESC
LIMIT :limit OFFSET :offset` for the page and a `SELECT count(*)` for the total, both
filtered by `bot_session_id`. This avoids loading the relationship. Ordering is by
`created_at` descending; ties are broken by `id` for a stable order across pages.

### Frontend paging state

`BotSessionPage.tsx` holds a zero-based page index in component state, derives
`offset = page * pageSize`, and passes `limit`/`offset` to the trades query (the query
key includes the page so React Query caches per page). Controls: **Previous** disabled
on the first page, **Next** disabled when `(page + 1) * pageSize >= total`, and a
"Page X of N" indicator (N = `ceil(total / pageSize)`, min 1). The existing empty state
renders when `total === 0`.

## Risks / Trade-offs

- Deep offsets are O(offset) in Postgres, but a paper-trading bot's ledger is small
  enough that this never matters; revisit with keyset paging only if a ledger grows to
  tens of thousands of rows.
- Page size is fixed (not user-selectable) to keep the UI minimal; can be added later
  without changing the API contract.

## Migration

None — no schema or data change.
