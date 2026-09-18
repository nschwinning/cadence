## Context

See proposal.md — Why. Today the AI build sets `create_portfolio(name=result.portfolio_name, ...)` in `ai_portfolio/service.py`, and the paper-trading views label sessions by `strategy_key`. The sibling trading-bot app already has a proven `name_generator` (Docker-style: risk profile + adjective + famous surname, with uniqueness-by-retry against a set of existing names). `PaperTradingSession` holds `portfolio_id` (FK to `portfolios.id`) but no name; `Portfolio.name` is the label. The `paper_trading` and `portfolios` model packages share one declarative `Base`, and `portfolios` does not import `paper_trading`, so a one-directional session→portfolio link introduces no import cycle.

## Goals / Non-Goals

- **Goals:** generate a distinct, human-friendly name for each newly built portfolio; surface the portfolio name on the session read model; label the two paper-trading views by portfolio name.
- **Non-Goals:** no rename of existing portfolios (only new builds get generated names); no DB migration; no denormalized copy of the name onto the session; no change to how sessions are keyed/created/archived; `strategy_key` stays in the payload and remains visible as secondary context. No batch/rename endpoint (trading-bot's bulk-rename route is out of scope).

## Decisions

- **Port `name_generator` into a backend utility, not a new dependency.** Add `cadence/utils/name_generator.py` with `ADJECTIVES`, a `FAMOUS_NAMES` list, and `generate_unique_name(risk_profile, existing_names, max_attempts)` — a faithful port of trading-bot's function (retry against `existing_names`, numeric-suffix fallback after `max_attempts`). It is a pure function → trivially unit-testable and deterministic under a seeded RNG.
  - *Alternative — an external name/petname library:* rejected; the word lists are tiny, the sibling app's version is proven, and a port keeps zero new dependencies and full control of the style.

- **Generate the name in the build flow, checking existing names from the DB.** In `ai_portfolio/service.py`, replace `name=result.portfolio_name` with a generated name: fetch existing portfolio names via a new `portfolios_service.list_portfolio_names(session)` helper, pass them and `params.risk_profile` to `generate_unique_name`. Uniqueness is best-effort at the application level (the retry loop + suffix fallback); we do not add a DB unique constraint on `portfolios.name` (would need a migration and could reject legitimate manual duplicates elsewhere).
  - *Alternative — keep the AI name and only add a metadata sub-line:* rejected by the user; names themselves must be distinct.
  - *Alternative — DB unique constraint on name:* rejected; out of scope (migration) and over-strict for a display label.

- **Discard the AI's `portfolio_name`; keep its thesis.** The generated name replaces `result.portfolio_name` for the stored `Portfolio.name`; the AI's `overall_thesis` continues to populate the portfolio description, so no reasoning is lost.

- **Expose the name via a view-only, eager-loaded relationship + accessor (no stored column).** Add `PaperTradingSession.portfolio = relationship("Portfolio", lazy="joined", viewonly=True)` and a `portfolio_name` property (`self.portfolio.name` or `None`); `PaperTradingSessionRead` gains `portfolio_name: str | None`, populated by `model_validate` via `from_attributes`. `lazy="joined"` keeps session listing a single round-trip (no N+1); `viewonly=True` because sessions never write through the link.
  - *Alternatives (denormalized column / service-layer join / client-side fetch):* rejected for the same reasons as above — migration weight, staleness, or N+1.

- **Null-safe fallback end to end.** Property returns `None` when unresolved; schema is `str | None`; the UI falls back to `strategy_key` when the name is null/empty.

## Risks / Trade-offs

- **Name collisions under concurrent builds** → the retry loop reads existing names within the build's transaction; two simultaneous builds could in theory pick the same name. Mitigation: the adjective×surname space is large and the suffix fallback makes exact collision improbable; the single-worker background executor further serializes AI builds in practice. Acceptable for a paper-trading tool; a DB constraint is deliberately out of scope.
- **Eager join on every session read** → one extra join against an indexed PK; negligible, and it removes the N+1 a lazy relationship would cause on the list.
- **Ported word lists drift from trading-bot** → acceptable; this is a copy, not a shared library, and the style only needs to be pleasant and varied.

## Migration Plan

No database migration. Existing portfolios keep their names; only new builds are affected. Backend and frontend ship together; the read field is additive, so an older frontend simply ignores it. Rollback is a code revert.
