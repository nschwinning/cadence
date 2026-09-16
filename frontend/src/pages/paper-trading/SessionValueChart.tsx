import { useSessionValueHistory } from '../../api/paperTrading';
import type { SessionValueSnapshot } from '../../types/api';
import { Panel } from './PaperTradingSessionPage';

/** Stroke colour by the equity curve's overall direction (first → last value). */
const TREND_STROKE = {
  up: '#059669',
  down: '#dc2626',
  flat: '#64748b',
} as const;

type Trend = keyof typeof TREND_STROKE;

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
  const values = snapshots.map((s) => s.total_value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  const points = snapshots.map((s, i) => {
    const x = pad + (i / (snapshots.length - 1)) * (width - 2 * pad);
    const y = pad + (1 - (s.total_value - min) / span) * (height - 2 * pad);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-40 w-full"
      role="img"
      aria-label={`Portfolio value over the last ${snapshots.length} daily snapshots`}
    >
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={TREND_STROKE[trendOf(snapshots)]}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
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
    >
      <div className="p-4">
        <ValueCurve snapshots={snapshots} />
      </div>
    </Panel>
  );
}

export default SessionValueChart;
