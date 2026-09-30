import { useState } from 'react';
import type { DashboardBreakdownEntry } from '../../types/api';
import { formatPercent } from '../../lib/format';
import { categoricalColor } from '../../lib/palette';

// A breakdown tile: a heading over a donut (ring) chart of the groups, sized by
// each group's share of the total. Slices and legend rows are hoverable and
// keyboard-focusable; the active one reveals its label, exact count, and
// percentage of the total (derived on the client from the counts). The donut
// center shows the total count. Renders an empty affordance when there are no
// groups.

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white p-6 shadow-sm';

// Donut geometry in a square viewBox (default preserveAspectRatio keeps circles
// round). pathLength=100 lets us express dash lengths directly as percentages.
const VIEWBOX = 100;
const CENTER = VIEWBOX / 2;
const RADIUS = 40;
const STROKE_WIDTH = 16;
const PATH_LENGTH = 100;

type Slice = {
  entry: DashboardBreakdownEntry;
  label: string;
  color: string;
  pct: number; // percentage of the total (0–100)
  offset: number; // cumulative percentage before this slice (0–100)
};

export function BreakdownTile({
  title,
  entries,
  /** Optional map from a raw key to a human-readable label. */
  formatKey,
}: {
  title: string;
  entries: DashboardBreakdownEntry[];
  formatKey?: (key: string) => string;
}) {
  const [activeKey, setActiveKey] = useState<string | null>(null);

  const total = entries.reduce((sum, e) => sum + e.count, 0);

  const label = (key: string) => (formatKey ? formatKey(key) : key);

  let cumulative = 0;
  const slices: Slice[] = entries.map((entry, index) => {
    const pct = total > 0 ? (entry.count / total) * 100 : 0;
    const slice: Slice = {
      entry,
      label: label(entry.key),
      color: categoricalColor(index),
      pct,
      offset: cumulative,
    };
    cumulative += pct;
    return slice;
  });

  const active = slices.find((s) => s.entry.key === activeKey) ?? null;

  const detail = (key: string) => {
    setActiveKey(key);
  };
  const clearDetail = () => setActiveKey(null);

  return (
    <section className={CARD_CLASS} aria-label={title}>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h3>

      {entries.length === 0 || total === 0 ? (
        <p className="mt-3 text-sm text-slate-400">No data yet</p>
      ) : (
        <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-center">
          {/* Donut */}
          <div className="relative mx-auto h-40 w-40 shrink-0">
            <svg
              viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`}
              className="h-full w-full"
              role="group"
              aria-label={`${title} breakdown, ${total.toLocaleString()} total`}
            >
              {/* Track */}
              <circle
                cx={CENTER}
                cy={CENTER}
                r={RADIUS}
                fill="none"
                stroke="#f1f5f9"
                strokeWidth={STROKE_WIDTH}
              />
              {/* Slices: rotate -90° so the first slice starts at 12 o'clock. */}
              <g transform={`rotate(-90 ${CENTER} ${CENTER})`}>
                {slices.map((s) => {
                  const isActive = s.entry.key === activeKey;
                  const dimmed = activeKey !== null && !isActive;
                  return (
                    <circle
                      key={s.entry.key}
                      cx={CENTER}
                      cy={CENTER}
                      r={RADIUS}
                      fill="none"
                      stroke={s.color}
                      strokeWidth={isActive ? STROKE_WIDTH + 3 : STROKE_WIDTH}
                      pathLength={PATH_LENGTH}
                      strokeDasharray={`${s.pct} ${PATH_LENGTH - s.pct}`}
                      strokeDashoffset={-s.offset}
                      opacity={dimmed ? 0.35 : 1}
                      tabIndex={0}
                      role="button"
                      aria-label={`${s.label}: ${s.entry.count.toLocaleString()} (${formatPercent(
                        s.pct / 100,
                        1,
                      )})`}
                      className="cursor-pointer outline-none transition-[stroke-width,opacity]"
                      onMouseEnter={() => detail(s.entry.key)}
                      onMouseLeave={clearDetail}
                      onFocus={() => detail(s.entry.key)}
                      onBlur={clearDetail}
                    />
                  );
                })}
              </g>
            </svg>
            {/* Center label: total, or the active slice's detail. */}
            <div
              className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center"
              aria-hidden="true"
            >
              {active ? (
                <>
                  <span className="max-w-[6rem] truncate text-xs font-medium text-slate-600">
                    {active.label}
                  </span>
                  <span className="text-lg font-bold tabular-nums text-slate-900">
                    {active.entry.count.toLocaleString()}
                  </span>
                  <span className="text-xs tabular-nums text-slate-500">
                    {formatPercent(active.pct / 100, 1)}
                  </span>
                </>
              ) : (
                <>
                  <span className="text-xl font-bold tabular-nums text-slate-900">
                    {total.toLocaleString()}
                  </span>
                  <span className="text-xs uppercase tracking-wide text-slate-500">
                    total
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Legend */}
          <ul className="flex min-w-0 flex-1 flex-col gap-1">
            {slices.map((s) => {
              const isActive = s.entry.key === activeKey;
              return (
                <li key={s.entry.key}>
                  <button
                    type="button"
                    className={`flex w-full items-center gap-2 rounded px-1 py-0.5 text-left outline-none focus:ring-1 focus:ring-slate-400 ${
                      isActive ? 'bg-slate-50' : ''
                    }`}
                    onMouseEnter={() => detail(s.entry.key)}
                    onMouseLeave={clearDetail}
                    onFocus={() => detail(s.entry.key)}
                    onBlur={clearDetail}
                    aria-label={`${s.label}: ${s.entry.count.toLocaleString()} (${formatPercent(
                      s.pct / 100,
                      1,
                    )})`}
                  >
                    <span
                      aria-hidden="true"
                      className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                      style={{ backgroundColor: s.color }}
                    />
                    <span className="min-w-0 flex-1 truncate text-sm text-slate-600">
                      {s.label}
                    </span>
                    <span className="text-sm font-semibold tabular-nums text-slate-900">
                      {s.entry.count.toLocaleString()}
                    </span>
                    <span className="w-14 shrink-0 text-right text-xs tabular-nums text-slate-500">
                      {formatPercent(s.pct / 100, 1)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

export default BreakdownTile;
