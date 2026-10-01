import type { DashboardSessionPerformance } from '../../types/api';
import { formatAxisDate, formatCurrency } from '../../lib/format';
import { categoricalColor } from '../../lib/palette';
import { ChartAxes } from '../paper-trading/ChartAxes';
import { combinedSeries } from './aggregate';

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white shadow-sm';
const LINE_COLOR = '#059669'; // emerald-600 — the single summed-value line

/**
 * The combined equity curve: a single dependency-free inline-SVG line summing
 * the checked sessions' values on a shared, carry-forward date axis windowed to
 * the selected range. Mirrors the native-SVG, non-scaling-stroke approach of the
 * paper-trading charts. The checkbox legend toggles the page-level selection
 * (which also re-derives the hero tiles and leaderboard), so this chart renders
 * from already-fetched per-session data and never refetches on a toggle.
 */
export function CombinedEquityChart({
  sessions,
  selectedIds,
  onToggle,
}: {
  sessions: DashboardSessionPerformance[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  const selected = sessions.filter((s) => selectedIds.has(s.id));
  const series = combinedSeries(selected);

  return (
    <div className={CARD_CLASS}>
      <div className="border-b border-slate-200 p-4">
        <h2 className="text-lg font-semibold text-slate-900">
          Combined equity curve
        </h2>
      </div>
      <div className="p-4">
        <SummedCurve points={series} hasSelection={selected.length > 0} />
        <Legend
          sessions={sessions}
          selectedIds={selectedIds}
          onToggle={onToggle}
        />
      </div>
    </div>
  );
}

/** The summed-value SVG line, with empty / insufficient-history placeholders. */
function SummedCurve({
  points,
  hasSelection,
}: {
  points: { date: string; value: number }[];
  hasSelection: boolean;
}) {
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
  if (points.length < 2) {
    return (
      <div
        className="flex h-40 items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400"
        data-testid="equity-placeholder"
      >
        Not enough history to plot yet.
      </div>
    );
  }

  const width = 800;
  const height = 160;
  const pad = 8;

  const times = points.map((p) => Date.parse(p.date));
  const values = points.map((p) => p.value);
  const minT = Math.min(...times);
  const maxT = Math.max(...times);
  const tSpan = maxT - minT || 1;
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const vSpan = maxV - minV || 1;

  const x = (t: number) => pad + ((t - minT) / tSpan) * (width - 2 * pad);
  const y = (value: number) =>
    pad + (1 - (value - minV) / vSpan) * (height - 2 * pad);

  const yLabels = [maxV, (minV + maxV) / 2, minV].map((v) => formatCurrency(v));
  const xLabels: [string, string] = [
    formatAxisDate(points[0].date),
    formatAxisDate(points[points.length - 1].date),
  ];

  return (
    <ChartAxes yLabels={yLabels} xLabels={xLabels}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="h-40 w-full"
        role="img"
        aria-label="Combined portfolio value"
      >
        <polyline
          points={points
            .map(
              (p) =>
                `${x(Date.parse(p.date)).toFixed(2)},${y(p.value).toFixed(2)}`,
            )
            .join(' ')}
          fill="none"
          stroke={LINE_COLOR}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
          data-testid="equity-line"
        />
      </svg>
    </ChartAxes>
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

export default CombinedEquityChart;
