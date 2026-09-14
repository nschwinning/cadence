import type { DashboardBreakdownEntry } from '../../types/api';

// A breakdown tile: a heading over a ranked list of key/count rows (largest
// first, as ordered by the backend). Counts use `tabular-nums` for alignment.
// Renders an explicit empty affordance when there are no groups.

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white p-6 shadow-sm';

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
  return (
    <section className={CARD_CLASS}>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h3>
      {entries.length === 0 ? (
        <p className="mt-3 text-sm text-slate-400">No data yet</p>
      ) : (
        <dl className="mt-3">
          {entries.map((entry) => (
            <div
              key={entry.key}
              className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0"
            >
              <dt className="truncate text-sm text-slate-600">
                {formatKey ? formatKey(entry.key) : entry.key}
              </dt>
              <dd className="text-sm font-semibold tabular-nums text-slate-900">
                {entry.count.toLocaleString()}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

export default BreakdownTile;
