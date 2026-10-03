import type { ReactNode } from 'react';

// A summary stat tile: a small uppercase label over a large value, on the same
// rounded white card used across the app. Numeric values use `tabular-nums` so
// figures align. The `compact` size shrinks the padding and fonts for dense
// grids (e.g. the paper-trading session KPIs); `default` keeps the larger look
// used on the dashboard.

type StatTileSize = 'default' | 'compact';

const CARD_CLASS: Record<StatTileSize, string> = {
  default: 'rounded-lg border border-slate-200 bg-white p-6 shadow-sm',
  compact: 'rounded-lg border border-slate-200 bg-white p-4 shadow-sm',
};
const LABEL_CLASS: Record<StatTileSize, string> = {
  default: 'text-xs font-semibold uppercase tracking-wide text-slate-500',
  compact: 'text-[0.65rem] font-semibold uppercase tracking-wide text-slate-500',
};
const VALUE_CLASS: Record<StatTileSize, string> = {
  default: 'mt-2 text-3xl font-bold tabular-nums text-slate-900',
  compact: 'mt-1 text-xl font-bold tabular-nums text-slate-900',
};
const HINT_CLASS: Record<StatTileSize, string> = {
  default: 'mt-1 text-sm text-slate-500',
  compact: 'mt-1 text-xs text-slate-500',
};

export function StatTile({
  label,
  value,
  hint,
  size = 'default',
}: {
  label: string;
  value: ReactNode;
  /** Optional muted line under the value (e.g. a unit or secondary figure). */
  hint?: ReactNode;
  /** Visual density. `compact` suits dense KPI grids. */
  size?: StatTileSize;
}) {
  return (
    <div className={CARD_CLASS[size]}>
      <p className={LABEL_CLASS[size]}>{label}</p>
      <p className={VALUE_CLASS[size]}>{value}</p>
      {hint && <p className={HINT_CLASS[size]}>{hint}</p>}
    </div>
  );
}

export default StatTile;
