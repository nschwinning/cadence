import { useMemo, useState } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import type {
  DashboardBenchmarkSeries,
  DashboardSessionPerformance,
} from '../../types/api';
import {
  formatAxisTimestamp,
  formatCurrency,
  formatTooltipTimestamp,
} from '../../lib/format';
import { categoricalColor } from '../../lib/palette';
import { EChart } from '../../components/charts/EChart';
import {
  combinedSeries,
  benchmarkDollarSeries,
  type CombinedPoint,
} from './aggregate';

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white shadow-sm';
const LINE_COLOR = '#059669'; // emerald-600 — the single summed-value line

// The benchmark id drawn by default; the rest are opt-in via the legend.
const DEFAULT_BENCHMARK_ID = 'SP500';

// Muted palette for the benchmark overlay lines, distinct from the emerald
// portfolio line. Assigned by a benchmark's position in the (stable) catalog so
// each index keeps its color regardless of which others are selected.
const BENCHMARK_COLORS = [
  '#64748b', // slate-500
  '#2563eb', // blue-600
  '#7c3aed', // violet-600
  '#0891b2', // cyan-600
  '#db2777', // pink-600
  '#ca8a04', // yellow-600
  '#9333ea', // purple-600
  '#0d9488', // teal-600
] as const;

/** One aggregated benchmark line ready to plot alongside the combined curve. */
interface BenchmarkLine {
  id: string;
  name: string;
  color: string;
  points: CombinedPoint[];
}

/**
 * Build the ECharts option for the combined equity curve: a single emerald line
 * summing the selected sessions' values, plus any selected benchmark index lines
 * (dashed, thinner, muted) — each the aggregated buy-and-hold of the selected
 * sessions' opening capital in that index — all on a shared time x-axis and USD
 * y-axis. The axis tooltip reports the summed value and each drawn benchmark's
 * value at the hovered date. Mirrors the paper-trading charts' EChart option shape
 * so the dashboard chart looks and behaves like them.
 */
export function buildCombinedOption(
  points: CombinedPoint[],
  benchmarkLines: BenchmarkLine[] = [],
): EChartsCoreOption {
  return {
    grid: { left: 64, right: 16, top: 12, bottom: 28 },
    xAxis: {
      type: 'time',
      axisLabel: {
        hideOverlap: true,
        formatter: (value: number) => formatAxisTimestamp(value),
      },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { formatter: (value: number) => formatCurrency(value) },
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const rows = Array.isArray(params) ? params : [params];
        if (rows.length === 0) return '';
        const first = rows[0] as { axisValue?: number };
        const ts = Number(first.axisValue);
        const header = formatTooltipTimestamp(ts);
        const lines: string[] = [header];
        for (const row of rows as Array<{
          seriesName?: string;
          value?: [number, number | null];
          marker?: string;
        }>) {
          const raw = Array.isArray(row.value) ? row.value[1] : null;
          if (raw === null || !Number.isFinite(raw)) continue;
          lines.push(
            `${row.marker ?? ''}${row.seriesName}: ${formatCurrency(raw)}`,
          );
        }
        return lines.length > 1 ? lines.join('<br/>') : header;
      },
    },
    series: [
      {
        id: 'combined',
        name: 'Combined value',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: LINE_COLOR },
        data: points.map((p) => [Date.parse(p.date), p.value]),
      },
      ...benchmarkLines.map((line) => ({
        id: `benchmark:${line.id}`,
        name: line.name,
        type: 'line' as const,
        showSymbol: false,
        lineStyle: { width: 1.5, type: 'dashed' as const },
        itemStyle: { color: line.color },
        data: line.points.map((p) => [Date.parse(p.date), p.value]),
      })),
    ],
  };
}

/**
 * The combined equity curve: a single line summing the checked sessions' values
 * on a shared, carry-forward date axis windowed to the selected range, with
 * selectable benchmark index lines — each the aggregated buy-and-hold of the
 * checked sessions' opening capital (and later increases) in that index. The
 * portfolio checkbox legend toggles the page-level selection (which also re-derives
 * the hero tiles and leaderboard); the benchmark checkbox legend toggles local
 * overlay state. Both render from already-fetched data and never refetch on a toggle.
 */
export function CombinedEquityChart({
  sessions,
  selectedIds,
  onToggle,
  benchmarkSeries,
}: {
  sessions: DashboardSessionPerformance[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  benchmarkSeries: DashboardBenchmarkSeries[];
}) {
  const selected = sessions.filter((s) => selectedIds.has(s.id));
  const series = combinedSeries(selected);

  // Local overlay selection: S&P 500 on by default, the rest opt-in.
  const [selectedBenchmarks, setSelectedBenchmarks] = useState<Set<string>>(
    () => new Set([DEFAULT_BENCHMARK_ID]),
  );
  const toggleBenchmark = (id: string) =>
    setSelectedBenchmarks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // Aggregate each selected, non-empty benchmark over exactly the checked sessions:
  // a buy-and-hold of each session's contributed capital in that index, summed and
  // evaluated on the combined curve's date axis. Re-runs when the session selection,
  // the overlay set, or the fetched data changes — no refetch. Colors are keyed to
  // catalog position for stability.
  const dateAxis = series.map((p) => p.date);
  const benchmarkLines = useMemo<BenchmarkLine[]>(() => {
    if (dateAxis.length === 0) return [];
    const lines: BenchmarkLine[] = [];
    benchmarkSeries.forEach((bench, i) => {
      if (!selectedBenchmarks.has(bench.benchmark_id)) return;
      const points = benchmarkDollarSeries(selected, bench.points, dateAxis);
      if (points.length === 0) return;
      lines.push({
        id: bench.benchmark_id,
        name: bench.name,
        color: BENCHMARK_COLORS[i % BENCHMARK_COLORS.length],
        points,
      });
    });
    return lines;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [benchmarkSeries, selectedBenchmarks, selected, dateAxis.join(',')]);

  return (
    <div className={CARD_CLASS}>
      <div className="border-b border-slate-200 p-4">
        <h2 className="text-lg font-semibold text-slate-900">
          Combined equity curve
        </h2>
      </div>
      <div className="p-4">
        <SummedCurve
          points={series}
          benchmarkLines={benchmarkLines}
          hasSelection={selected.length > 0}
        />
        <Legend
          sessions={sessions}
          selectedIds={selectedIds}
          onToggle={onToggle}
        />
        <BenchmarkLegend
          benchmarkSeries={benchmarkSeries}
          selectedBenchmarks={selectedBenchmarks}
          onToggle={toggleBenchmark}
        />
      </div>
    </div>
  );
}

/** The summed-value chart, with empty / insufficient-history placeholders. */
function SummedCurve({
  points,
  benchmarkLines,
  hasSelection,
}: {
  points: CombinedPoint[];
  benchmarkLines: BenchmarkLine[];
  hasSelection: boolean;
}) {
  // Only build the option once there is something to plot; the empty/placeholder
  // states return first so the chart never mounts on a degenerate series.
  const option = useMemo(
    () => (points.length >= 2 ? buildCombinedOption(points, benchmarkLines) : null),
    [points, benchmarkLines],
  );

  if (!hasSelection) {
    return (
      <div
        className="flex h-40 items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400"
        data-testid="equity-empty"
      >
        Select at least one portfolio to plot.
      </div>
    );
  }
  if (points.length < 2 || option === null) {
    return (
      <div
        className="flex h-40 items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400"
        data-testid="equity-placeholder"
      >
        Not enough history to plot yet.
      </div>
    );
  }
  return (
    <EChart
      option={option}
      height={200}
      className="w-full"
      ariaLabel="Combined portfolio value"
    />
  );
}

/** Checkbox legend of every active session; toggling drives the selection. */
function Legend({
  sessions,
  selectedIds,
  onToggle,
}: {
  sessions: DashboardSessionPerformance[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  return (
    <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm">
      {sessions.map((s, i) => {
        const checked = selectedIds.has(s.id);
        return (
          <li key={s.id}>
            <label
              className={`flex cursor-pointer items-center gap-2 ${
                checked ? 'text-slate-700' : 'text-slate-400'
              }`}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => onToggle(s.id)}
                className="h-3.5 w-3.5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              <span
                aria-hidden="true"
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: categoricalColor(i) }}
              />
              <span className="font-medium">{s.label}</span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Checkbox legend of every catalog benchmark. A benchmark with no price data over
 * the range is disabled (its checkbox is inert) rather than erroring. Toggling an
 * enabled benchmark adds or removes its aggregated overlay line without a refetch.
 */
function BenchmarkLegend({
  benchmarkSeries,
  selectedBenchmarks,
  onToggle,
}: {
  benchmarkSeries: DashboardBenchmarkSeries[];
  selectedBenchmarks: Set<string>;
  onToggle: (id: string) => void;
}) {
  if (benchmarkSeries.length === 0) return null;
  return (
    <ul
      className="mt-3 flex flex-wrap gap-x-4 gap-y-2 border-t border-slate-100 pt-3 text-sm"
      aria-label="Benchmark indexes"
    >
      {benchmarkSeries.map((bench, i) => {
        const checked = selectedBenchmarks.has(bench.benchmark_id);
        const hasData = bench.points.length > 0;
        return (
          <li key={bench.benchmark_id}>
            <label
              className={`flex items-center gap-2 ${
                !hasData
                  ? 'cursor-not-allowed text-slate-300'
                  : checked
                    ? 'cursor-pointer text-slate-700'
                    : 'cursor-pointer text-slate-400'
              }`}
            >
              <input
                type="checkbox"
                checked={checked && hasData}
                disabled={!hasData}
                onChange={() => onToggle(bench.benchmark_id)}
                className="h-3.5 w-3.5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 disabled:opacity-50"
              />
              <span
                aria-hidden="true"
                className="inline-block h-0 w-3 border-t-2 border-dashed"
                style={{ borderColor: BENCHMARK_COLORS[i % BENCHMARK_COLORS.length] }}
              />
              <span className="font-medium">{bench.name}</span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}

export default CombinedEquityChart;
