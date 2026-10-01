import { Link } from 'react-router-dom';
import type { DashboardAutomationSummary } from '../../types/api';
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

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${statusPillClass(
        status,
      )}`}
    >
      {status.toLowerCase()}
    </span>
  );
}

/**
 * Global automation panel: the latest rebalance run (status, relative time, link
 * to its run), an in-flight indicator, the count of failed runs within the range,
 * and the next approximate cron run (noting it ignores market holidays).
 */
export function AutomationPanel({
  automation,
}: {
  automation: DashboardAutomationSummary;
}) {
  const { latest_run, in_flight, failed_in_range, next_run_approx } = automation;

  return (
    <div className={CARD_CLASS}>
      <div className="flex items-baseline gap-3 border-b border-slate-200 p-4">
        <h2 className="text-lg font-semibold text-slate-900">Automation</h2>
        {in_flight && (
          <span
            className="inline-flex items-center gap-1.5 text-sm text-amber-700"
            role="status"
          >
            <span
              aria-hidden="true"
              className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-500"
            />
            Rebalance in progress
          </span>
        )}
      </div>
      <dl className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Last rebalance
          </dt>
          <dd className="mt-1 text-sm text-slate-700">
            {latest_run ? (
              <span className="flex flex-wrap items-center gap-2">
                <StatusPill status={latest_run.status} />
                <Link
                  to={`/runs/${latest_run.id}`}
                  className="text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
                >
                  {formatRelativeTime(latest_run.created_at)}
                </Link>
              </span>
            ) : (
              <span className="text-slate-400">No rebalance runs yet</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Failed runs (range)
          </dt>
          <dd
            className={`mt-1 text-2xl font-bold tabular-nums ${
              failed_in_range > 0 ? 'text-red-700' : 'text-slate-900'
            }`}
          >
            {failed_in_range.toLocaleString()}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Next run (approx.)
          </dt>
          <dd className="mt-1 text-sm text-slate-700">
            {new Date(next_run_approx).toLocaleString()}
            <span className="ml-1 text-slate-400">
              — scheduled estimate, ignores market holidays
            </span>
          </dd>
        </div>
      </dl>
    </div>
  );
}

export default AutomationPanel;
