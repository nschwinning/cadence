## Context

See proposal.md — Why. The Dashboard combined equity curve (`CombinedEquityChart.tsx`) was recently migrated to the shared Apache ECharts wrapper and plots a single emerald line summing the selected sessions' values. The dashboard overview is backend-computed per active session (`dashboard/service.py::_session_performance`); the client holds the selection and re-aggregates the summed line, hero tiles, and leaderboard without refetching.

The app already ingests and stores daily prices for every catalog benchmark (`benchmark_prices` table, populated by `ingest_benchmark_prices` which loops the whole `Benchmark` enum), and has reusable series helpers in `paper_trading/benchmark.py` (`load_benchmark_series`, `rebased_benchmark_value`). A `GET /paper-trading/benchmarks` catalog endpoint and a frontend `useBenchmarks` hook already exist and give index display names. No price data or migration is needed — only a new seam to surface the windowed price series on the overview and draw rebased lines on the client.

## Goals / Non-Goals

**Goals:**
- Surface per-index benchmark price series (date + price), windowed to the selected range, on the overview payload.
- Draw benchmark lines on the combined curve rebased to the *visible* combined curve's start, selectable via a legend, S&P 500 on by default, with no refetch on toggle.

**Non-Goals:**
- No percent/dollar toggle on the dashboard chart (explicitly rejected by the user; the chart stays dollar-only).
- No change to the per-session benchmark machinery, the per-session value-history chart, or the `GET /paper-trading/benchmarks` endpoint.
- No new benchmark catalog or persistence; no migration.
- No contribution-aware benchmark overlay (capital-increase events). The combined curve is a summed-value line, and benchmark lines rebase to its single starting point only — matching the chart's current summed-value semantics, not the per-session time-weighted benchmark overlay.

## Decisions

### Decision 1 — Send raw index price series, rebase on the client (not server-side pre-rebased overlays)

The central design choice. The combined curve's starting date and value depend on **which sessions the client has selected** — selection is client-only state, and changing it moves the summed line's first point. A benchmark line is only a meaningful comparison when it starts from the **same starting capital as the visible line**. Two options:

- **(A) Server pre-rebases** each index once against a fixed anchor (e.g. the all-active-sessions combined curve) and sends ready-to-plot overlay points. Simplest client, but the benchmark baseline would not match the visible summed curve's start whenever the user selects a subset — the lines would start from a different dollar value than the portfolio line, defeating the comparison.
- **(B) Server sends the windowed index *price* series** (date + price); the client rebases each selected index to the currently-visible combined curve's first `[date, value]` whenever selection or the legend changes. Faithful: every benchmark line always starts exactly where the visible portfolio line starts, and re-rebases on selection change for free.

**Chosen: (B).** It is the only option that preserves "same starting capital as the visible curve" under arbitrary session selection, and it keeps the legend/selection toggles pure client-side show/hide — consistent with the existing architecture where the session selection re-derives everything from already-fetched data without refetching. The extra payload is small (≤8 indexes × range-length daily points) and is fetched once with the overview.

Client rebasing: for a benchmark with prices `p(t)` and the combined curve starting at `(t0, V0)`, the rebased line value at date `t` is `V0 × p(t) / p(t0*)`, where `t0*` is the first benchmark date on or at/after `t0` that has a price (anchor to the index's first available price at/after the combined start). Only plot benchmark points on dates at/after `t0`. If the index has no price at/after `t0`, draw no line.

### Decision 2 — Overview payload shape: a new overview-level `benchmark_series` list

Add an overview-level field (not per-session), e.g. `benchmark_series: list[DashboardBenchmarkSeries]` where each entry is `{ benchmark_id: str, name: str, points: list[DashboardBenchmarkPricePoint{date, price}] }`. Edit **both** the service dataclass and the parallel Pydantic schema in `api/schemas.py` (they are maintained in lockstep). Build the list in the overview assembly by iterating the `Benchmark` catalog and calling the existing `load_benchmark_series` per index, windowed to the same range bounds already computed for the per-session value series. An index with no points over the range yields an entry with an empty `points` list (never omitted, never an error).

Reuse the display name from the existing benchmark catalog helper so `name` matches what `GET /paper-trading/benchmarks` returns; the frontend can equally read names from `useBenchmarks`, but carrying `name` on the series keeps the overlay self-contained.

### Decision 3 — Benchmark legend as a second checkbox group on the same chart

Reuse the existing per-session checkbox-legend pattern already in `CombinedEquityChart.tsx`. Add a separate benchmark legend group driven by a client-side `Set<benchmarkId>` initialized to `{ SP500 }`. A benchmark whose series has no points over the range renders its checkbox disabled/inert. `buildCombinedOption` grows to accept the selected, already-rebased benchmark lines and emit one ECharts line series each — dashed, thinner, and in muted palette colors distinct from the emerald portfolio line — plus extend the axis-trigger tooltip to report each drawn line's value. German date formatting (`formatAxisTimestamp`/`formatTooltipTimestamp`) is unchanged.

## Risks / Trade-offs

- **[Payload growth]** Up to 8 full daily price series on every overview fetch (largest at the `Max` range). → Points are just `{date, price}`; 8 × a few hundred points is small JSON, fetched once per range change, and avoids per-toggle requests. If it ever matters, the series are trivially cacheable server-side.
- **[Rebasing anchor mismatch]** The combined curve's first date may fall on a non-trading day or before an index's first stored price. → Anchor each index to its first available price at/after the combined start; if none exists, draw no line (inert legend control) rather than guessing.
- **[Visual clutter]** All 8 indexes at once would be noisy. → Only S&P 500 is on by default; the rest are opt-in via the legend, matching the user's decision.
- **[Semantic nuance]** The combined curve is a summed-value line without contribution adjustment, so a benchmark rebased to its start is a simple "same starting dollars in the index" comparison, not a contribution-aware time-weighted benchmark. → Intentional (Non-Goal); it matches the chart's existing summed-value meaning and keeps the comparison legible.
