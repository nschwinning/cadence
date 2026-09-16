import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  DEFAULT_SESSIONS_PARAMS,
  useArchiveSession,
  useSessions,
  useUnarchiveSession,
} from '../../api/paperTrading';
import type { PaperTradingSession } from '../../types/api';

/** Format a EUR value with no fraction digits. */
const eurFormatter = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
});

/** Status pill colors per session status. */
const STATUS_STYLES: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-800',
  paused: 'bg-amber-100 text-amber-800',
  stopped: 'bg-slate-100 text-slate-700',
};

function StatusBadge({ status }: { status: string }) {
  const className = STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-700';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${className}`}
    >
      {status}
    </span>
  );
}

function SessionRow({ session }: { session: PaperTradingSession }) {
  const archive = useArchiveSession();
  const unarchive = useUnarchiveSession();
  const isArchived = session.archived_at !== null;
  const busy = archive.isPending || unarchive.isPending;
  const pnlClass =
    session.total_pnl > 0
      ? 'text-emerald-700'
      : session.total_pnl < 0
        ? 'text-red-700'
        : 'text-slate-700';
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3 font-semibold">
        <Link
          to={`/paper-trading/${session.id}`}
          className="text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          {session.strategy_key}
        </Link>
        {isArchived && (
          <span className="ml-2 inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
            Archived
          </span>
        )}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={session.status} />
      </td>
      <td className="px-4 py-3 text-slate-700">{session.schedule_mode}</td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {eurFormatter.format(session.allocated_capital)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {session.total_trades}
      </td>
      <td className={`px-4 py-3 text-right tabular-nums font-medium ${pnlClass}`}>
        {eurFormatter.format(session.total_pnl)}
      </td>
      <td className="px-4 py-3 text-slate-500">
        {session.last_run_at
          ? new Date(session.last_run_at).toLocaleString()
          : '—'}
      </td>
      <td className="px-4 py-3 text-right">
        {isArchived ? (
          <button
            type="button"
            onClick={() => unarchive.mutate(session.id)}
            disabled={busy}
            className="rounded border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            Unarchive
          </button>
        ) : session.status === 'stopped' ? (
          <button
            type="button"
            onClick={() => archive.mutate(session.id)}
            disabled={busy}
            className="rounded border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            Archive
          </button>
        ) : (
          <span className="text-slate-300">—</span>
        )}
      </td>
    </tr>
  );
}

export function PaperTradingPage() {
  const [showArchived, setShowArchived] = useState(false);
  const { data, isPending, isError } = useSessions({
    ...DEFAULT_SESSIONS_PARAMS,
    includeArchived: showArchived,
  });
  const sessions = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">
        Paper Trading
      </h1>

      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-3 border-b border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">Sessions</h2>
          {!isPending && !isError && total > 0 && (
            <span className="text-sm text-slate-500">{total} total</span>
          )}
          <label className="ml-auto flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(event) => setShowArchived(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Show archived
          </label>
        </div>

        {isPending && (
          <p role="status" aria-live="polite" className="p-6 text-slate-500">
            Loading sessions…
          </p>
        )}

        {isError && (
          <div
            role="alert"
            className="m-4 rounded border border-red-300 bg-red-50 p-4 text-red-800"
          >
            <p className="font-semibold">Could not load sessions</p>
            <p className="mt-1 text-sm">Please try again later.</p>
          </div>
        )}

        {!isPending && !isError && sessions.length === 0 && (
          <p className="p-6 text-slate-500">
            No paper-trading sessions yet. Build an AI portfolio to start one.
          </p>
        )}

        {!isPending && !isError && sessions.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Strategy</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Schedule</th>
                  <th className="px-4 py-3 text-right">Capital</th>
                  <th className="px-4 py-3 text-right">Trades</th>
                  <th className="px-4 py-3 text-right">P&amp;L</th>
                  <th className="px-4 py-3">Last Run</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((session) => (
                  <SessionRow key={session.id} session={session} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export default PaperTradingPage;
