import type { ReactNode } from 'react';

// A summary stat tile: a small uppercase label over a large value, on the same
// rounded white card used across the app. Numeric values use `tabular-nums` so
// figures align.

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white p-6 shadow-sm';
const LABEL_CLASS =
  'text-xs font-semibold uppercase tracking-wide text-slate-500';

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  /** Optional muted line under the value (e.g. a unit or secondary figure). */
  hint?: ReactNode;
}) {
  return (
    <div className={CARD_CLASS}>
      <p className={LABEL_CLASS}>{label}</p>
      <p className="mt-2 text-3xl font-bold tabular-nums text-slate-900">
        {value}
      </p>
      {hint && <p className="mt-1 text-sm text-slate-500">{hint}</p>}
    </div>
  );
}

export default StatTile;
