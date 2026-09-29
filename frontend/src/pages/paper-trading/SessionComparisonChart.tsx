import { useState } from 'react';
import { useSessionsValueComparison } from '../../api/paperTrading';
import type { SessionValueComparisonSeries } from '../../types/api';
import { formatCurrency, formatPercent } from '../../lib/format';
import { Panel } from './PaperTradingSessionPage';

/** Which metric the comparison chart plots. */
type Metric = 'return' | 'value';

/**
 * Categorical palette assigned per session by list order, so each session keeps
 * a stable colour across both metrics and in the legend (including legend-only
 * sessions that are not plotted).
 */
const SERIES_PALETTE = [
  '#2563eb',
  '#059669',
  '#d97706',
  '#dc2626',
  '#7c3aed',
  '#0891b2',
  '#db2777',
  '#65a30d',
] as const;

function colorFor(index: number): string {
  return SERIES_PALETTE[index % SERIES_PALETTE.length];
}

/** A single plotted point in the current metric's units, on a calendar x-axis. */
interface PlotPoint {
  t: number;
  value: number;
}

/** A session prepared for plotting: its colour, label, and metric-space points. */
interface PlotSeries {
  id: string;
  label: string;
  color: string;
  points: PlotPoint[];
}

/**
 * Convert one session's raw points into metric-space plot points. For the return
 * metric a session with non-positive allocated capital cannot be normalised, so
 * it yields no points (and thus drops to legend-only).
 */
function toPlotSeries(
  series: SessionValueComparisonSeries,
  index: number,
  metric: Metric,
): PlotSeries {
  const canReturn = metric === 'return' && series.allocated_capital > 0;
  const points: PlotPoint[] =
    metric === 'value' || canReturn
      ? series.points.map((p) => ({
          t: Date.parse(p.snapshot_date),
          value:
            metric === 'value'
              ? p.total_value
              : (p.total_value - series.allocated_capital) /
                series.allocated_capital,
        }))
      : [];
  return {
    id: series.session_id,
    label: series.label,
    color: colorFor(index),
    points,
  };
}

/**
 * A dependency-free inline-SVG multi-line chart overlaying every plottable
 * session on a shared calendar x-domain and a shared per-metric y-domain. Mirrors
 * `SessionValueChart`'s native-SVG, non-scaling-stroke approach. Sessions with
 * fewer than two plottable points are not drawn (they still appear in the legend).
 */
function ComparisonCurves({
  series,
  metric,
}: {
  series: PlotSeries[];
  metric: Metric;
}) {
  const plottable = series.filter((s) => s.points.length >= 2);

  if (plottable.length === 0) {
    return (
      <div
        className="flex h-40 items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400"
        data-testid="comparison-placeholder"
      >
        Not enough history to compare yet.
      </div>
    );
  }

  const width = 800;
  const height = 160;
  const pad = 8;

  const allPoints = plottable.flatMap((s) => s.points);
  const times = allPoints.map((p) => p.t);
  const values = allPoints.map((p) => p.value);
  const minT = Math.min(...times);
  const maxT = Math.max(...times);
  const tSpan = maxT - minT || 1;
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const vSpan = maxV - minV || 1;

  const x = (t: number) => pad + ((t - minT) / tSpan) * (width - 2 * pad);
  const y = (value: number) =>
    pad + (1 - (value - minV) / vSpan) * (height - 2 * pad);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-40 w-full"
      role="img"
      aria-label={`Session comparison by ${
        metric === 'return' ? 'return percent' : 'portfolio value'
      }`}
    >
      {plottable.map((s) => (
        <polyline
          key={s.id}
          points={s.points
            .map((p) => `${x(p.t).toFixed(2)},${y(p.value).toFixed(2)}`)
            .join(' ')}
          fill="none"
          stroke={s.color}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
          aria-label={s.label}
          data-testid="comparison-line"
        />
      ))}
    </svg>
  );
}

/** Colour-swatch legend mapping each session to its line colour. */
function Legend({
  series,
  metric,
}: {
  series: PlotSeries[];
  metric: Metric;
}) {
  return (
    <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm">
      {series.map((s) => {
        const plotted = s.points.length >= 2;
        const latest = s.points[s.points.length - 1];
        const summary =
          plotted && latest
            ? metric === 'return'
              ? formatPercent(latest.value)
              : formatCurrency(latest.value)
            : 'no chart data';
        return (
          <li
            key={s.id}
            className={`flex items-center gap-2 ${
              plotted ? 'text-slate-700' : 'text-slate-400'
            }`}
          >
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            <span className="font-medium">{s.label}</span>
            <span className="text-slate-400">· {summary}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Panel comparing every non-archived session's performance over time, with a
 * %/$ toggle (defaulting to normalised return %) so sessions with different
 * capital and start dates can be compared fairly.
 */
export function SessionComparisonChart() {
  const [metric, setMetric] = useState<Metric>('return');
  const { data, isPending, isError } = useSessionsValueComparison();
  const sessions = data?.sessions ?? [];
  const series = sessions.map((s, i) => toPlotSeries(s, i, metric));

  return (
    <Panel
      title="Session comparison"
      count={sessions.length}
      isPending={isPending}
      isError={isError}
      isEmpty={sessions.length === 0}
      emptyText="No sessions to compare yet."
    >
      <div className="p-4">
        <div
          role="group"
          aria-label="Comparison metric"
          className="mb-4 inline-flex overflow-hidden rounded border border-slate-300 text-sm"
        >
          <button
            type="button"
            aria-pressed={metric === 'return'}
            onClick={() => setMetric('return')}
            className={`px-3 py-1 font-medium ${
              metric === 'return'
                ? 'bg-emerald-600 text-white'
                : 'bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            Return %
          </button>
          <button
            type="button"
            aria-pressed={metric === 'value'}
            onClick={() => setMetric('value')}
            className={`border-l border-slate-300 px-3 py-1 font-medium ${
              metric === 'value'
                ? 'bg-emerald-600 text-white'
                : 'bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            Value $
          </button>
        </div>
        <ComparisonCurves series={series} metric={metric} />
        <Legend series={series} metric={metric} />
      </div>
    </Panel>
  );
}

export default SessionComparisonChart;
