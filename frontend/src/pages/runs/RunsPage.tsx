import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAIRuns } from '../../api/aiPortfolio';
import type { AIPortfolioEvent } from '../../types/api';

/** Format an ISO timestamp for display, or an em dash when absent. */
function ts(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : '—';
}

const EVENT_STATUS_STYLES: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-700',
  running: 'bg-sky-100 text-sky-800',
  succeeded: 'bg-emerald-100 text-emerald-800',
  partial: 'bg-amber-100 text-amber-800',
  skipped: 'bg-slate-100 text-slate-600',
  failed: 'bg-red-100 text-red-800',
};

function EventStatusBadge({ status }: { status: string }) {
  const className = EVENT_STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-700';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${className}`}
    >
      {status}
    </span>
  );
}

/** Which run types the history can be filtered to. */
type TypeFilter = 'all' | 'build' | 'rebalance' | 'close';

const TYPE_FILTERS: { value: TypeFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'build', label: 'Builds' },
  { value: 'rebalance', label: 'Rebalances' },
  { value: 'close', label: 'Closes' },
];

function RunRow({ run }: { run: AIPortfolioEvent }) {
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3 font-semibold">
        <Link
          to={`/runs/${run.id}`}
          className="text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          {ts(run.created_at)}
        </Link>
      </td>
      <td className="px-4 py-3 capitalize text-slate-700">{run.event_type}</td>
      <td className="px-4 py-3">
        <EventStatusBadge status={run.status} />
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {run.actions_taken?.length ?? 0}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {run.research?.length ?? 0}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-500">
        {run.duration_ms === null ? '—' : `${run.duration_ms} ms`}
      </td>
      <td className="px-4 py-3">
        {run.session_id ? (
          <Link
            to={`/paper-trading/${run.session_id}`}
            className="text-emerald-700 hover:underline"
          >
            Session
          </Link>
        ) : (
          <span className="text-slate-400">—</span>
        )}
      </td>
    </tr>
  );
}

export function RunsPage() {
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');
  const { data, isPending, isError } = useAIRuns({
    eventType: typeFilter === 'all' ? undefined : typeFilter,
  });
  const runs = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">
        AI Runs
      </h1>

      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">History</h2>
          {!isPending && !isError && total > 0 && (
            <span className="text-sm text-slate-500">{total} total</span>
          )}
          <div className="ml-auto inline-flex rounded-md border border-slate-200 p-0.5">
            {TYPE_FILTERS.map((f) => (
              <button
                key={f.value}
                type="button"
                onClick={() => setTypeFilter(f.value)}
                aria-pressed={typeFilter === f.value}
                className={`rounded px-3 py-1 text-sm font-medium ${
                  typeFilter === f.value
                    ? 'bg-emerald-500 text-white'
                    : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {isPending && (
          <p role="status" aria-live="polite" className="p-6 text-slate-500">
            Loading runs…
          </p>
        )}

        {isError && (
          <div
            role="alert"
            className="m-4 rounded border border-red-300 bg-red-50 p-4 text-red-800"
          >
            <p className="font-semibold">Could not load runs</p>
            <p className="mt-1 text-sm">Please try again later.</p>
          </div>
        )}

        {!isPending && !isError && runs.length === 0 && (
          <p className="p-6 text-slate-500">
            No AI runs yet. Build or rebalance an AI portfolio to record one.
          </p>
        )}

        {!isPending && !isError && runs.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Run</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                  <th className="px-4 py-3 text-right">Searches</th>
                  <th className="px-4 py-3 text-right">Duration</th>
                  <th className="px-4 py-3">Session</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <RunRow key={run.id} run={run} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export default RunsPage;
