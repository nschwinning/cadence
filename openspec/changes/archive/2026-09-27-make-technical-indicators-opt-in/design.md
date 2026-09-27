## Context

See proposal.md — Why. The technical-indicator trend strategy (build entry gate,
rebalance candidate hard-filter, holdings reversal context, per-run trend-decision
context) is currently unconditional. It was added in
`archive/2026-09-27-add-technical-indicator-trend-strategy`. Sessions already persist
several build-time choices that are *frozen* for the session's lifetime — asset scope
(`session_metadata`), risk profile (`session_metadata`), and rebalance-prompt version
(dedicated non-nullable column `rebalance_prompt_version`). The gating logic lives in
`ai_portfolio/service.py` (`_candidates_from_universe`, `_build_holdings`, and the
build candidate assembly), which read the latest stored `technical_indicator`
snapshot per asset. The nightly compute job (`technical_indicators/`) is independent
and universe-wide.

## Goals / Non-Goals

**Goals:**
- A per-session boolean, chosen at build time and frozen, that turns the whole trend
  strategy on or off for that session.
- Default off (opt-in) for new builds; all existing sessions treated as off.
- When off: build and rebalance both behave as the pre-trend flow (no gate, no
  indicator/reversal annotations, no trend-decision context recorded).
- When on: current trend behavior, unchanged.

**Non-Goals:**
- No change to the nightly indicator computation job or stored snapshots.
- No change to the AI output schema or the executor.
- No per-run or post-build toggling — the choice is frozen at build (like asset scope
  and prompt version). Changing it later is out of scope.

## Decisions

- **Storage: dedicated non-nullable column, not `session_metadata`.** Add
  `use_technical_indicators: bool` to `paper_trading_sessions`, mirroring
  `rebalance_prompt_version` (a frozen build-time choice). A dedicated column gives a
  clean non-nullable default + backfill and is trivially queryable, versus burying a
  flag in the JSON `session_metadata` blob (where asset scope/risk profile live as
  softer, nullable values). Migration: `down_revision` = current head
  `c3d4e5f6a7b8`; add column with `server_default="false"`, backfill existing rows to
  `false`, then keep the default so inserts are safe.
- **Default off resolved in two places.** The Pydantic build request field defaults to
  `False`, and `create_session` writes the value; a session read back with no value
  (legacy path) is treated as `False`. This matches the "no persisted X ⇒ safe
  default" pattern already used for asset scope and risk profile.
- **Single branch point in the service.** Read `session.use_technical_indicators`
  once in `run_build_event` / `run_rebalance_event` and pass it down; the candidate
  assembly and holdings builder apply the gate/annotations only when true. When
  false they return the pre-trend candidate/holdings shape and `trend_context` stays
  `None` (which already yields absent `run_stats.gate` and no trend-decision context —
  no extra handling needed downstream).
- **Freeze at build, like the prompt version.** `run_build_event` captures the flag
  from the request and persists it on the session; `run_rebalance_event` reads the
  frozen flag. No request field on the rebalance path.
- **API/UI surface.** Add the field to `AIPortfolioBuildRequest` and
  `AIBuildParams`, expose it on `PaperTradingSessionRead` (read-only), and add a
  default-off toggle to the build form. The run-detail trend-decision section already
  hides itself when context is absent, so opted-out sessions need no UI guard there.

## Risks / Trade-offs

- **Test DB rebuild.** A new non-nullable column means the persistent `cadence_test`
  DB must be dropped once so conftest `create_all` rebuilds it (same as prior
  new-column changes). Migration backfill itself isn't exercised by the test harness
  (tests use `create_all`, not migrations), so verify the backfill via manual SQL /
  `alembic` round-trip.
- **Behavioral break for freshly built trend sessions.** Any session built during the
  trend rollout (before this change) is "existing" and will be backfilled to off,
  losing the gate. This is the intended backward-compatible default; if a user wants
  those to keep gating they must rebuild. Called out so it is not a surprise.
- **Two-path branching risk.** The gate logic now has on/off paths; tests must cover
  both for build and rebalance to prevent the off-path silently keeping (or the
  on-path silently dropping) behavior.
