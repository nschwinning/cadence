# Design

## Context

The paper-trading session carries a `use_technical_indicators: boolean` field,
chosen at build time and frozen on the session. It is already:

- returned by the backend on `PaperTradingSessionRead`, and
- present on the frontend TypeScript `PaperTradingSession` type
  (`frontend/src/types/api.ts`).

What is missing is purely the read-only surfacing of this flag on the session
detail header, where every sibling opt-in already has a fact tile.

## Decision

Add one fact tile to the `SessionHeader` `<dl>` in
`frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`, rendered exactly
like the existing **Company fundamentals** and **Watchlist assets** tiles:

```tsx
<div>
  <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
    Technical indicators
  </dt>
  <dd className="text-sm text-slate-900">
    {session.use_technical_indicators ? 'On' : 'Off'}
  </dd>
</div>
```

Placement: alongside the other opt-in tiles (e.g. immediately after the
**Watchlist assets** tile), before the Model/Scope tiles. Exact ordering is a
minor presentational detail; grouping it with the other strategy opt-ins keeps
the header coherent.

## Rationale

- **Consistency over novelty.** This mirrors the established On/Off fact-tile
  pattern (stop-loss, guardrails, learning feedback, fundamentals, watchlist),
  so there is no new interaction, data flow, or styling decision.
- **No backend work.** The flag is already on the read model and the TS type, so
  the change is a single JSX tile plus a test assertion. No API/schema/migration.

## Alternatives considered

- **Show richer trend context (e.g. per-asset trend state) on the session page.**
  Out of scope — that data is per-asset and already lives on the asset detail
  page's technical section. This change only echoes the session's frozen opt-in,
  matching the other config tiles.

## Risks

- None material. The flag is non-nullable on the read model; `'On'`/`'Off'` has
  no undefined/edge path. The only test impact is an added assertion in the
  existing `PaperTradingSessionPage` test (the existing `getAllByText('Off')`
  count-based assertions must be updated for the new default-off tile).
