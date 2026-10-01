## Context

See proposal.md — Why. The technical-indicator config lives only in
`backend/src/cadence/technical_indicators/constants.py` (indicator periods, gate
thresholds, reversal-flag thresholds). The only HTTP surface for the capability
today is the cron-guarded `POST /api/v1/technical-indicators/runs`. The spec
requires the config be readable over an unauthenticated endpoint and rendered in
an info-only page. No ORM or snapshot data is involved — this is a pure
projection of module constants into a JSON response.

## Goals / Non-Goals

**Goals:**
- Serve the configured indicator set, periods, gate rules + thresholds, and
  reversal-flag definitions + thresholds from the backend as read-only JSON.
- Keep the page truthful to `constants.py` — the response is derived from the
  constants, not a duplicated hand-maintained copy.
- Add a conventional nav tab + page following existing app-shell patterns.

**Non-Goals:**
- No per-asset indicator snapshots (that data exists via
  `service.get_latest_snapshots` but is out of scope for this info page).
- No editing of thresholds from the UI.
- No change to the nightly precompute job or the cron-guarded runs endpoint.
- No database migration.

## Decisions

### Config assembly: a service builder reading constants, not literals in the schema
The read path is `router → service.get_indicator_config() → schema`. A new
`service.get_indicator_config()` (pure, no DB session) assembles a plain
structure from the `constants.py` values, and the router returns it validated
through a new `TechnicalIndicatorConfig` Pydantic schema in `api/schemas.py`.
*Why:* keeps the router thin (project convention) and makes the response a
projection of the constants, so tuning a constant changes the API without
editing the schema. *Alternative considered:* inlining literals in the schema
defaults — rejected because it duplicates the constants and silently drifts.

### Response shape: grouped, self-describing sections
The schema groups the payload into: `indicators` (a list of
`{key, label, params}` where `params` carries the relevant period/lookback
values per indicator), `trend_gate` (`regime` conditions, `momentum`
conditions, the soft `obv_rising` bonus note, and the "missing required
indicator fails the gate" rule), and `reversal_flags` (a list of
`{key, label, description}` plus the `rsi_overbought` and `slope_flatten_eps`
thresholds). *Why:* the frontend renders readable grouped sections directly from
this without re-deriving meaning; labels/descriptions are human-readable text so
the page needs no hard-coded copy of the rules. *Alternative:* returning the raw
flat constants dict — rejected because the page would then have to hard-code the
grouping and wording, defeating the "driven by backend" goal.

### Frontend follows the dashboard read pattern
New `frontend/src/api/technicalIndicators.ts` (query-key factory + raw async fn +
`useTechnicalIndicatorConfig()` `useQuery` hook), a matching type in
`types/api.ts`, and a `pages/technical-indicators/TechnicalIndicatorsPage.tsx`
that renders grouped sections with loading/error states. Nav entry added to
`components/layout/Sidebar.tsx` with a new icon under `components/icons/`; route
added in `App.tsx` inside the `Layout` route. *Why:* mirrors `api/dashboard.ts`
and the existing pages exactly — lowest-surprise, consistent with the shell.

## Risks / Trade-offs

- [Config drift between backend labels and indicator math] → The service builds
  the config next to `constants.py` and references the same names; a unit test
  asserts the endpoint reports the current constant values so a renamed/removed
  constant fails the test rather than silently misreporting.
- [Unauthenticated endpoint exposes strategy internals] → Accepted: the values
  are non-sensitive tunables, the endpoint is read-only and cannot trigger
  computation, and transparency to the user is the point.
- [Page copy could go stale] → Mitigated by sourcing labels/descriptions from
  the backend response rather than hard-coding them in the component.
