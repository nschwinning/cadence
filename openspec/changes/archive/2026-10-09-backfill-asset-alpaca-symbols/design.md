## Context

See proposal.md — Why. The `Asset.alpaca_symbol` column already exists (migration `c4e7a1f9b2d3`, nullable, no backfill). `add_asset` populates it at add-time via `broker.get_asset(ticker, asset_class)` → `BrokerAsset.symbol`. There is already a direct precedent for exactly this kind of one-off fill: `backfill_fractionable(session, broker)` in `assets/service.py`, which iterates rows where `Asset.fractionable IS NULL`, looks each up on the brokerage once, stores the flag, swallows per-asset errors, commits once, and returns a count. That helper was shipped by `add-fractional-equity-sizing` and is invoked by the operator post-deploy (not wired to an endpoint). This change adds a sibling for `alpaca_symbol`.

## Goals / Non-Goals

**Goals:**
- Clear the false-positive not-tradable flags on legacy rows by resolving their brokerage symbol, while keeping genuinely-foreign listings (AIR.PA, TTE.PA) flagged.
- Match the established `backfill_fractionable` shape, conventions, and test style so the two read as a matched pair.

**Non-Goals:**
- No Alembic data migration (external I/O must not run inside a migration).
- No new endpoint, CLI entrypoint, cron, or startup hook — operator invokes the helper once, exactly as the fractional backfill is invoked.
- No re-verification or clearing of already-populated (non-null) symbols.
- No change to the not-tradable badge or AI-panel logic — they become correct once the data is filled.

## Decisions

- **Sibling service helper, not a migration.** `backfill_alpaca_symbols(session, broker) -> int` lives next to `backfill_fractionable` and copies its structure: `select(Asset).where(Asset.alpaca_symbol.is_(None))`, per-asset `try/except Exception` with `logger.warning(...)` + `continue`, `asset_class` derived from `asset.category` (CRYPTO vs EQUITY), `session.commit()` only if any row changed, return the update count. Rationale: migrations own schema and must stay deterministic/offline-safe; services own external I/O. Alternative (Alembic data migration) rejected — it would couple deploys to Alpaca reachability and credentials.
- **Resolve-and-set, tradable-gated.** Store `broker_asset.symbol` only when `broker_asset is not None and broker_asset.tradable`. Mirrors `add_asset`'s tradability gate so the backfill reaches the same verdict a fresh add would. A null/absent/not-tradable result leaves the row NULL (still flagged) — which is the correct outcome for AIR.PA/TTE.PA. (Note: `backfill_fractionable` only null-checks because a listed-but-untradable asset can still report fractionable; here tradability is the whole point, so the gate is included.)
- **Idempotent by construction.** Because it only selects `alpaca_symbol IS NULL`, a re-run skips everything already filled and retries only the still-null rows (e.g. ones that failed transiently or were offline). No separate bookkeeping needed.
- **Operator-invoked, no new surface.** Shipped as a helper only; the operator runs it once post-deploy via a short one-off (e.g. `uv run python -c "..."` that builds a session + real broker and calls the helper), the same way the fractional backfill is run. Keeps the change minimal and avoids inventing an endpoint/CLI pattern the project does not yet have.

## Risks / Trade-offs

- [Brokerage offline / rate-limited during the run] → Fail-open + idempotent: failed rows stay NULL and the operator simply re-runs later; one failure never aborts the pass. Same posture as `backfill_fractionable`.
- [A symbol that legitimately differs from the ticker (e.g. `BRK-B` → `BRK.B`)] → Stored as the brokerage's canonical `symbol`, not the ticker — exactly what add-time verification does; covered by a test asserting the differing symbol is persisted.
- [Helper has no runnable entrypoint in-repo] → Accepted, matching the fractional precedent; the operator invokes it directly. If a first-class entrypoint is wanted later, it is a separate, additive change.
