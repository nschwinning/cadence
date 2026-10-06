## Context

See `proposal.md` — Why. The load-bearing current-state facts (verified in code):

- `allocated_capital` is a NOT-NULL `Float` on `PaperTradingSession` (`paper_trading/models.py:103-105`), set once in `create_session` (`paper_trading/service.py:74-144`) and never mutated.
- Session cash is **derived**, not stored: `compute_session_value` (`paper_trading/service.py:1030-1102`) returns `total_value = allocated_capital + realized_pnl − total_fees + Σ unrealized`, `cash_value = total_value − positions_value`. So raising `allocated_capital` by +X raises cash by X automatically, and the next rebalance (which sizes against live `valuation.total_value`, `ai_portfolio/service.py:1033/1041`) deploys it. No executor change is needed to make added capital investable.
- All return analytics treat `allocated_capital` as one fixed basis: KPIs `total_return_pct = (total_value − allocated)/allocated` (`service.py:1591-1592`), Sharpe from the stored `daily_pnl_pct` series (`service.py:859-877` spec), the benchmark overlay rebases `allocated_capital` to the first snapshot date (`benchmark.py:137-158`), and `record_value_snapshot` measures the first day's P&L against `allocated_capital` (`service.py:1283-1286`).
- There is no capital-events table and no time-weighting today. The mutation pattern to mirror is `change_session_benchmark` (service `service.py:240-265`, router `PUT /sessions/{id}/benchmark` `api/routers/paper_trading.py:342-364`, request `SessionBenchmarkChangeRequest` `schemas.py:658-661`, error `InvalidBenchmarkError`).
- Current Alembic head: `b5f1a2c3d4e6`.

## Goals / Non-Goals

**Goals:**
- Let an operator add capital to a running session and have the added cash become investable, without starting a new session.
- Keep every reported return honest across a capital increase by (a) recording *when* capital was contributed and (b) computing returns time-weighted and contribution-aware.
- Preserve the meaning of `allocated_capital` as "total contributed capital" so every existing read (Capital tile, list page, comparison chart, rebalance sizing) keeps working unchanged.
- Backward compatibility: a session that never gets a capital increase must report exactly what it reports today.

**Non-Goals:**
- No withdrawals / decreases (increase-only).
- No re-pricing or rewriting of already-stored historical snapshots.
- No intraday contribution timing — contribution effective dates are day-granular, which is sufficient for a manual, infrequent operator action and for a daily snapshot series.
- No automatic immediate rebalance on contribution — added cash waits for the next scheduled rebalance (which already sizes against live value).
- No change to build-time sizing (build has already happened for any session that can be topped up).

## Decisions

### D1: Capital-events ledger table, with the original capital as an implicit baseline

New table `session_capital_events`: `id` (PK), `session_id` (FK → `paper_trading_sessions`, indexed), `amount` (Float, > 0), `effective_date` (Date), `created_at` (DateTime). A capital increase appends one row and, in the same transaction, bumps `session_row.allocated_capital += amount`.

The session's **contribution set** used by all analytics is derived, not fully stored:
`contributions = {(start_date, allocated_capital − Σ event.amount)} ∪ {(e.effective_date, e.amount) for e in events}`.
The synthetic first element is the original build capital (current `allocated_capital` minus the recorded increases). This needs **no data backfill**: a legacy or never-topped-up session has no event rows, so its contribution set is just `{(start_date, allocated_capital)}` and every formula below collapses to today's behavior.

*Alternatives considered:* (a) backfill a baseline row per existing session at migration — rejected, unnecessary data migration and a second source of truth for the original amount; (b) store only `allocated_capital` deltas without dates — rejected, TWR and the benchmark overlay need the dates; (c) no `allocated_capital` denormalization, sum events on every read — rejected, would churn every existing read and sizing path. Keeping `allocated_capital` as the running sum is the minimal-blast-radius choice.

### D2: Time-weighted return from the daily NAV series, contribution-adjusted

Build a daily return series from the ordered snapshots: for each snapshot day `d` with NAV `V_d` and contributions `C_d` effective that day,
`r_d = (V_d − C_d − V_{d−1}) / V_{d−1}`, with `V_{d−1}` for the first day being the original baseline contributed capital. Append a final point using the live marked-to-market value (from `compute_session_value`) net of any contribution since the last snapshot.

- `total_return_pct` (TWR) = `Π(1 + r_d) − 1`.
- Sharpe uses the same `r_d` series (mean/stdev, annualised) — unchanged formula, contribution-adjusted input.
- `max_drawdown` is computed over the cumulative growth index `g_d = Π_{i≤d}(1 + r_i)` rather than raw NAV, so a contribution does not look like a jump or a recovery.
- Absolute `total_return` stays `current_value − allocated_capital` (= current value − total contributed), which is already contribution-neutral because we bump `allocated_capital`.

For a session with no contributions after baseline, `r_d` reduces to the existing daily return and the chained product equals the simple return — so behavior is unchanged. This is asserted by a dedicated test.

*Alternatives considered:* money-weighted return (IRR) — rejected, the user chose TWR and TWR is the standard way to neutralize external cash flows for performance comparison; splitting sub-periods only at contribution boundaries using pre-contribution snapshots — folded into the daily-series approach, which is simpler and already day-granular.

### D3: Benchmark is contribution-aware for the dollar overlay, unchanged for the KPI fraction

- **Value-history overlay (dollars)** — `rebased_benchmark_value` becomes contribution-aware: `benchmark_value(t) = Σ_c c.amount × close(t)/close(d_c)` over contributions with `d_c ≤ t`. The benchmark "buys units" with each contribution at that date's price, so the dollar benchmark line receives the same cash the session did and stays a fair overlay against the session's (money-weighted, dollar) value curve. For a single contribution this is identical to today's rebased line.
- **KPI `benchmark_return_pct` (fraction)** — unchanged. A benchmark is a single buy-and-hold instrument, so its per-dollar (time-weighted) return over `[start, latest]` is `close(latest)/close(start) − 1` regardless of cash flows. `excess_return_pct = session_TWR − benchmark_return_pct` — both sides time-weighted, so the comparison is apples-to-apples. `excess_return` (dollars) = `excess_return_pct × allocated_capital`.

`benchmark_return_fraction` (`benchmark.py:161-179`) is untouched; only `rebased_benchmark_value` and its callers (`list_value_history` `service.py:1356-1387`, dashboard narrative `ai_portfolio/service.py:1795-1798`) take the contribution list.

### D4: Operation surface — `POST`, increase-only

`POST /api/v1/paper-trading/sessions/{session_id}/capital`, body `SessionCapitalIncreaseRequest { amount: float = Field(gt=0) }`, returns `PaperTradingSessionRead`. POST (not PUT) because each call appends a contribution — it is not idempotent. Service `increase_session_capital(session, *, session_id, amount)`: `get_session` → `SessionNotFoundError` (404); `amount <= 0` → new `InvalidCapitalChangeError` (422, also enforced by the schema's `gt=0`); insert event row; `allocated_capital += amount`; commit; refresh; return. No broker dependency (nothing is bought or sold on contribution). Frontend: `changeSessionCapital` raw fn + `useIncreaseSessionCapital` hook invalidating `paperTradingKeys.all`, `.kpis(id)`, `.valueHistory(id)`; an "Add capital" numeric input + button near the Capital fact tile (`PaperTradingSessionPage.tsx:603`), mirroring `BenchmarkSwitcher`/`ScopeSwitcher` with isPending/isError feedback.

### D5: `record_value_snapshot` excludes same-day contributions from the day's P&L

Going forward, `record_value_snapshot` (`service.py:1265-1300`) subtracts contributions effective on the snapshot's date from the day's P&L (`daily_pnl`/`daily_pnl_pct`), so a day capital is added is not reported as a gain in the snapshot or the daily report. Historical snapshots are left as-is (no contributions existed before this change).

## Risks / Trade-offs

- **Stored `daily_pnl_pct` vs recomputed series** → KPIs/Sharpe recompute the contribution-adjusted `r_d` series at read time from snapshot NAVs + the contribution set, rather than trusting historically stored per-day percents. This keeps correctness independent of when a snapshot was written.
- **Daily granularity for the TWR split** → a contribution is attributed to its effective date, and the pre-contribution value is the prior day's snapshot. Acceptable: contributions are infrequent manual actions and the whole series is daily. Documented as a non-goal to go intraday.
- **Two different contribution treatments (dollar overlay is money-weighted; KPI fractions are time-weighted)** → intentional and documented in D3: the dollar chart line must receive the same cash to be comparable to the session's dollar value, while the headline percentages must be time-weighted to be comparable across deposits. A code comment will state this to prevent a future "bug fix" that wrongly unifies them.
- **`allocated_capital` now mutable** → every path that reads it keeps working because it still means total contributed capital; the only new invariant is "`allocated_capital` == original baseline + Σ event.amount", maintained transactionally in `increase_session_capital`. A test asserts the invariant.
- **Legacy/no-increase sessions** → contribution set is a single baseline; TWR = simple return, benchmark overlay = today's rebased line. A regression test pins this equivalence.

## Migration Plan

1. Add the `SessionCapitalEvent` ORM model and an Alembic migration `add_session_capital_events` with `down_revision = "b5f1a2c3d4e6"` (verify the head at implementation time). `upgrade` creates the table + the `session_id` index; `downgrade` drops them. No data backfill (D1).
2. Round-trip the migration: `uv run alembic upgrade head`, `uv run alembic downgrade -1`, `uv run alembic upgrade head`, and `uv run alembic check` (no drift) — keep the single linear head.
3. Ship backend + frontend together; the feature is additive and defaults to today's behavior for every session until an increase is recorded. Rollback is dropping the migration (no session loses data — `allocated_capital` already held the total).
