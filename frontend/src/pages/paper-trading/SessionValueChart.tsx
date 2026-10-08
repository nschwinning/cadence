import { useSessionValueHistory } from '../../api/paperTrading';
import type { SessionValueSnapshot } from '../../types/api';
import { formatAxisDate, formatCurrency } from '../../lib/format';
import { ChartAxes } from './ChartAxes';
import { FreshnessBadge, Panel } from './PaperTradingSessionPage';

/** Stroke colour by the equity curve's overall direction (first → last value). */
const TREND_STROKE = {
  up: '#059669',
  down: '#dc2626',
  flat: '#64748b',
} as const;

type Trend = keyof typeof TREND_STROKE;

/** Stroke colour for the benchmark overlay line (neutral amber, distinct from trend). */
const BENCHMARK_STROKE = '#d97706';

function trendOf(snapshots: SessionValueSnapshot[]): Trend {
  const first = snapshots[0].total_value;
  const last = snapshots[snapshots.length - 1].total_value;
  if (last > first) return 'up';
  if (last < first) return 'down';
  return 'flat';
}

/**
 * A dependency-free inline-SVG line chart of a session's total value over time.
 * Mirrors the asset detail page's `PriceSparkline`: native SVG, utility-only
 * styling, and a dashed placeholder until there are at least two points to plot.
 */
function ValueCurve({ snapshots }: { snapshots: SessionValueSnapshot[] }) {
  if (snapshots.length < 2) {
    return (
      <div className="flex h-40 items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400">
        Not enough history to chart yet.
      </div>
    );
  }

  const width = 800;
  const height = 160;
  const pad = 8;

  // Benchmark is a second series rebased to the same units as total_value, so both
  // share one y-scale. Only snapshots with a non-null benchmark value are plotted;
  // when every value is null the overlay is omitted entirely.
  const hasBenchmark = snapshots.some((s) => s.benchmark_value !== null);
  const benchmarkValues = snapshots
    .map((s) => s.benchmark_value)
    .filter((v): v is number => v !== null);

  const values = snapshots.map((s) => s.total_value);
  const min = Math.min(...values, ...benchmarkValues);
  const max = Math.max(...values, ...benchmarkValues);
  const span = max - min || 1;

  const x = (i: number) => pad + (i / (snapshots.length - 1)) * (width - 2 * pad);
  const y = (value: number) =>
    pad + (1 - (value - min) / span) * (height - 2 * pad);

  const points = snapshots.map(
    (s, i) => `${x(i).toFixed(2)},${y(s.total_value).toFixed(2)}`,
  );
  const benchmarkPoints = snapshots
    .map((s, i) =>
      s.benchmark_value !== null
        ? `${x(i).toFixed(2)},${y(s.benchmark_value).toFixed(2)}`
        : null,
    )
    .filter((p): p is string => p !== null);

  const benchmarkDrawn = hasBenchmark && benchmarkPoints.length >= 2;
  const trendStroke = TREND_STROKE[trendOf(snapshots)];

  // Three USD y-ticks (top→bottom) from the shared value scale, and the first/last
  // snapshot dates on the x-axis — rendered as HTML around the SVG by `ChartAxes`.
  const yLabels = [max, (min + max) / 2, min].map((v) => formatCurrency(v));
  const xLabels: [string, string] = [
    formatAxisDate(snapshots[0].snapshot_date),
    formatAxisDate(snapshots[snapshots.length - 1].snapshot_date),
  ];

  return (
    <div>
      <ChartAxes yLabels={yLabels} xLabels={xLabels}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="h-40 w-full"
          role="img"
          aria-label={`Portfolio value over the last ${snapshots.length} daily snapshots`}
        >
          {benchmarkDrawn && (
            <polyline
              points={benchmarkPoints.join(' ')}
              fill="none"
              stroke={BENCHMARK_STROKE}
              strokeWidth={1.5}
              strokeDasharray="4 3"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
              aria-label="Benchmark value"
              data-testid="benchmark-line"
            />
          )}
          <polyline
            points={points.join(' ')}
            fill="none"
            stroke={trendStroke}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </ChartAxes>
      <ValueLegend trendStroke={trendStroke} benchmarkDrawn={benchmarkDrawn} />
    </div>
  );
}

/**
 * Legend naming the two lines on the value chart. The benchmark entry appears only
 * when the benchmark line is actually drawn, so the legend never implies a line that
 * is not on the chart.
 */
function ValueLegend({
  trendStroke,
  benchmarkDrawn,
}: {
  trendStroke: string;
  benchmarkDrawn: boolean;
}) {
  return (
    <ul
      className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm text-slate-700"
      data-testid="value-legend"
    >
      <li className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="inline-block h-2.5 w-2.5 rounded-full"
          style={{ backgroundColor: trendStroke }}
        />
        <span className="font-medium">Portfolio value</span>
      </li>
      {benchmarkDrawn && (
        <li className="flex items-center gap-2" data-testid="benchmark-legend">
          <span
            aria-hidden="true"
            className="inline-block h-0.5 w-4"
            style={{
              backgroundImage: `repeating-linear-gradient(to right, ${BENCHMARK_STROKE} 0 4px, transparent 4px 7px)`,
            }}
          />
          <span className="font-medium">Benchmark</span>
        </li>
      )}
    </ul>
  );
}

/** Panel showing the session's end-of-day portfolio value as a line chart. */
export function SessionValueChart({ sessionId }: { sessionId: string }) {
  const { data, isPending, isError } = useSessionValueHistory(sessionId);
  const snapshots = data?.items ?? [];
  return (
    <Panel
      title="Portfolio value"
      count={data?.total}
      isPending={isPending}
      isError={isError}
      isEmpty={false}
      emptyText="No value history yet."
      badge={<FreshnessBadge kind="eod" />}
    >
      <div className="p-4">
        <ValueCurve snapshots={snapshots} />
      </div>
    </Panel>
  );
}

export default SessionValueChart;
