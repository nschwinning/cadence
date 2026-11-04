## 1. Backend — shared benchmark-returns helper

- [x] 1.1 In `backend/src/cadence/strategy_bots/service.py`, add a private helper
  `_bot_benchmark_returns(session, bot, snapshots, *, total_return_pct, as_of) ->
  tuple[float | None, float | None]` returning `(benchmark_return_pct,
  excess_return_pct)` — load the series via `load_benchmark_series`, compute the
  since-inception fraction via `benchmark_return_fraction(start_date=snapshots[0]
  .snapshot_date, as_of=as_of)`, and excess as `total_return_pct - benchmark_return_pct`
  (both `None` when no snapshots or the fraction is `None`). Verify `uv run mypy
  src/cadence` is clean.
- [x] 1.2 Refactor `_bot_benchmark_suffix` to obtain its benchmark/excess from the new
  helper and format the existing string unchanged. Verify the existing notification
  tests still pass unchanged (`uv run pytest -k benchmark_suffix` or the relevant
  notification test) — output byte-identical.

## 2. Backend — KPI fields

- [x] 2.1 Add `benchmark: str`, `benchmark_return_pct: float | None`, and
  `excess_return_pct: float | None` to the `BotKpis` dataclass in `service.py`.
- [x] 2.2 In `bot_session_kpis`, populate the three fields: `benchmark=bot.benchmark`,
  and `benchmark_return_pct`/`excess_return_pct` from `_bot_benchmark_returns(...,
  total_return_pct=total_return_pct, as_of=datetime.now(UTC).date())`. Verify with a new
  unit test that KPIs include a non-None benchmark/excess for a session with a seeded
  benchmark series + snapshot, and `None` for a session with no snapshot.
- [x] 2.3 Add `benchmark: str`, `benchmark_return_pct: float | None`, and
  `excess_return_pct: float | None` to `BotKpisRead` in
  `backend/src/cadence/api/schemas.py` (keep `total_fees`). Verify the KPIs endpoint
  serializes the new fields (extend an existing `/bots/sessions/{id}/kpis` API test).
- [x] 2.4 Run `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run
  pytest` — all green.

## 3. Frontend — types and tile

- [x] 3.1 In `frontend/src/types/api.ts`, add `benchmark: string`,
  `benchmark_return_pct: number | null`, and `excess_return_pct: number | null` to the
  `BotKpis` interface. Verify `npx tsc --noEmit` is clean.
- [x] 3.2 In `frontend/src/pages/bots/BotSessionPage.tsx`, remove the "Transaction fees"
  `KpiTile` and add a benchmark-comparison tile in its place: resolve the benchmark
  display name from the `useBenchmarks` catalog (fallback to the id); label `vs {name}`,
  value = `excess_return_pct` via `formatPercent` coloured with `pnlClass`, hint =
  `benchmark_return_pct` rendered as `Benchmark {pct}, buy & hold`. When
  `benchmark_return_pct === null`, render value `—` with a "Needs a daily snapshot" hint.
- [x] 3.3 Add/adjust `BotSessionPage` tests: the Performance section renders the
  "vs {benchmark}" excess tile and NO "Transaction fees" tile, and a session with a null
  benchmark return renders the em-dash placeholder. Verify `cd frontend && npx vitest
  run` passes.
- [x] 3.4 Run `cd frontend && npx vitest run && npx tsc --noEmit` — all green.

## 4. Verification

- [x] 4.1 Full backend gate green (`ruff` + `mypy` + `pytest`) and full frontend gate
  green (`vitest` + `tsc`), confirming the benchmark tile replaces the fees tile
  end-to-end with no regressions.
