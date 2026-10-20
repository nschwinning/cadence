import { Link } from 'react-router-dom';
import type { DashboardActivityEntry } from '../../types/api';
import { formatRelativeTime } from '../../lib/format';

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white shadow-sm';

/** Per-status pill colours, matching the paper-trading status convention. */
function statusPillClass(status: string): string {
  const s = status.toLowerCase();
  if (s === 'completed' || s === 'success')
    return 'bg-emerald-100 text-emerald-800';
  if (s === 'running' || s === 'pending') return 'bg-amber-100 text-amber-800';
  if (s === 'failed' || s === 'error') return 'bg-red-100 text-red-800';
  if (s === 'partial') return 'bg-amber-100 text-amber-800';
  return 'bg-slate-100 text-slate-700';
}

/**
 * Global recent-activity feed: AI runs (build / rebalance / close) across all
 * sessions within the selected range, newest first and capped by the backend.
 * Each entry links to its run detail page.
 */
export function RecentActivityFeed({
  entries,
}: {
  entries: DashboardActivityEntry[];
}) {
  return (
    <div className={CARD_CLASS}>
      <div className="flex items-baseline gap-3 border-b border-slate-200 p-4">
        <h2 className="text-lg font-semibold text-slate-900">Recent activity</h2>
        {entries.length > 0 && (
          <span className="text-sm text-slate-500">{entries.length} runs</span>
        )}
      </div>
      {entries.length === 0 ? (
        <p className="p-6 text-slate-500">No activity in this range.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {entries.map((e) => (
            // Fixed-width status/kind columns keep every row's cells aligned into
            // the same columns regardless of pill text length; the label flexes
            // (truncating) and the time pins to the right.
            <li
              key={e.id}
              className="grid grid-cols-[6rem_6rem_1fr_auto] items-center gap-x-3 px-4 py-3 text-sm"
            >
              <span
                className={`inline-flex w-fit items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${statusPillClass(
                  e.status,
                )}`}
              >
                {e.status.toLowerCase()}
              </span>
              <span className="truncate font-medium capitalize text-slate-700">
                {e.kind.toLowerCase()}
              </span>
              <span className="truncate text-slate-500">
                {e.session_label ?? '—'}
              </span>
              <Link
                to={`/runs/${e.id}`}
                className="justify-self-end whitespace-nowrap text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {formatRelativeTime(e.created_at)}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default RecentActivityFeed;
