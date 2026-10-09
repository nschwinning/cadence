## Why

The Assets page shows *what* is in the universe (the composition donuts) but offers
no qualitative read on whether the universe is well-constructed — its
diversification, concentration, quality, gaps, and risks. An AI assessment gives
the operator a plain-language judgement at a glance, and because the universe
drifts over time (assets added/removed, nightly metric refresh), the assessment
needs to tell the operator when it has gone stale.

## What Changes

- Add an AI-generated **asset universe evaluation**: a markdown narrative plus
  bulleted strengths / concerns / suggestions assessing the whole universe
  (diversification, sector/category concentration, quality, notable gaps, and
  foreign/unpriceable listings). No numeric scores.
- **Persist** a single current evaluation in the database (new table + Alembic
  migration): the generated content, a `generated_at` timestamp, and a
  **content fingerprint** of the universe captured at generation time. Refresh
  replaces the record; no history is kept.
- **Lazy fill once when empty**: when no evaluation exists, generate one on first
  read.
- **Manual refresh**: an operator-triggered regenerate action replaces the stored
  evaluation, its fingerprint, and its timestamp. No other automatic regeneration.
- **Outdated detection**: on read, recompute the universe fingerprint and compare
  it to the stored one; when they differ the evaluation is flagged outdated. The
  fingerprint hashes every asset's mutable columns, so it flips on membership
  changes *and* on the nightly metric refresh (the operator's chosen "any asset
  change" semantics — the `assets` table has no `updated_at` column, so a content
  hash is used rather than a timestamp watermark).
- Reuse the existing OpenAI agent infrastructure (the same SDK + model settings as
  the recommender / AI rebalance prompts); add it behind the project's injectable
  Protocol pattern so tests run without network access.
- **Frontend**: a panel on the Assets page directly below the composition donuts
  that renders the narrative + findings and the `generated_at` time, shows an
  "Outdated" warning when the universe has changed since generation, and provides a
  Refresh control with a loading state. On first load with no evaluation it
  auto-triggers generation.

## Capabilities

### New Capabilities
<!-- none; this extends existing capabilities -->

### Modified Capabilities
- `assets`: add requirements for generating, persisting, lazy-filling, refreshing,
  and staleness-detecting an AI evaluation of the whole asset universe, exposed via
  read + refresh API endpoints.
- `app-shell`: add a requirement for the Assets-page AI universe evaluation panel
  (rendered under the composition donuts) with its outdated warning, refresh
  control, and first-load auto-generation.

## Impact

- **Backend**: new `assets` persistence (ORM model + Alembic migration chained off
  the current head), new service logic (fingerprint, generate, lazy-init, refresh,
  outdated check), a new evaluation agent behind an injectable Protocol with a
  fake for tests, new Pydantic schemas in `api/schemas.py`, and new routes on the
  assets router (`GET` current evaluation with an `outdated` flag; `POST` refresh).
- **Frontend**: a new evaluation panel component on the Assets page, a typed
  api-client + TanStack Query hooks (read + refresh mutation), new entries in
  `types/api.ts`, and markdown rendering for the narrative. Adds a markdown
  rendering approach (dependency or minimal renderer) if none exists.
- **Config / external**: uses `OPENAI_API_KEY` and the existing AI model setting;
  one additional OpenAI call per generation (initial fill + manual refreshes only).
- **No change** to order execution, sessions, or the nightly jobs themselves
  (the evaluation only *reads* the universe state the refresh produces).
