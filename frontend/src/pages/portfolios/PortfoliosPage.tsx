import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  DEFAULT_PORTFOLIOS_PARAMS,
  useArchivePortfolio,
  usePortfolios,
  useUnarchivePortfolio,
} from '../../api/portfolios';
import { useSessions } from '../../api/paperTrading';
import { BuildAIPortfolioCard } from './BuildAIPortfolioCard';
import type { Portfolio } from '../../types/api';

/** Turn a raw source/risk slug into a display label. */
function humanize(value: string | null): string {
  if (!value) return '—';
  return value.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function PortfolioRow({
  portfolio,
  blocked,
}: {
  portfolio: Portfolio;
  /** True when the portfolio has an active or paused session (not archivable). */
  blocked: boolean;
}) {
  const archive = useArchivePortfolio();
  const unarchive = useUnarchivePortfolio();
  const isArchived = portfolio.archived_at !== null;
  const busy = archive.isPending || unarchive.isPending;
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3 font-semibold">
        <Link
          to={`/portfolios/${portfolio.id}`}
          className="text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          {portfolio.name}
        </Link>
        {isArchived && (
          <span className="ml-2 inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
            Archived
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-slate-700">{humanize(portfolio.source)}</td>
      <td className="px-4 py-3 text-slate-700">
        {humanize(portfolio.risk_profile)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {portfolio.stocks.length}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {(portfolio.max_allocation_pct * 100).toFixed(0)}%
      </td>
      <td className="px-4 py-3 text-slate-500">
        {new Date(portfolio.created_at).toLocaleDateString()}
      </td>
      <td className="px-4 py-3 text-right">
        {isArchived ? (
          <button
            type="button"
            onClick={() => unarchive.mutate(portfolio.id)}
            disabled={busy}
            className="rounded border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            Unarchive
          </button>
        ) : blocked ? (
          <span
            className="text-xs text-slate-400"
            title="Archive after all its sessions are stopped."
          >
            In use
          </span>
        ) : (
          <button
            type="button"
            onClick={() => archive.mutate(portfolio.id)}
            disabled={busy}
            className="rounded border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            Archive
          </button>
        )}
      </td>
    </tr>
  );
}

export function PortfoliosPage() {
  const [showArchived, setShowArchived] = useState(false);
  const { data, isPending, isError } = usePortfolios({
    ...DEFAULT_PORTFOLIOS_PARAMS,
    includeArchived: showArchived,
  });
  const portfolios = data?.items ?? [];
  const total = data?.total ?? 0;

  // A portfolio can only be archived once none of its sessions are active or
  // paused. Derive the blocked set from the sessions list (archived sessions are
  // always stopped, so the default list is sufficient).
  const { data: sessionsData } = useSessions();
  const blockedPortfolioIds = useMemo(() => {
    const blocked = new Set<string>();
    for (const s of sessionsData?.items ?? []) {
      if (s.status === 'active' || s.status === 'paused') {
        blocked.add(s.portfolio_id);
      }
    }
    return blocked;
  }, [sessionsData]);

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">
        Portfolios
      </h1>

      <BuildAIPortfolioCard />

      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-3 border-b border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">
            Stored portfolios
          </h2>
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
            Loading portfolios…
          </p>
        )}

        {isError && (
          <div
            role="alert"
            className="m-4 rounded border border-red-300 bg-red-50 p-4 text-red-800"
          >
            <p className="font-semibold">Could not load portfolios</p>
            <p className="mt-1 text-sm">Please try again later.</p>
          </div>
        )}

        {!isPending && !isError && portfolios.length === 0 && (
          <p className="p-6 text-slate-500">
            No portfolios yet. Build an AI portfolio above to get started.
          </p>
        )}

        {!isPending && !isError && portfolios.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">Risk</th>
                  <th className="px-4 py-3 text-right">Holdings</th>
                  <th className="px-4 py-3 text-right">Max Alloc</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {portfolios.map((portfolio) => (
                  <PortfolioRow
                    key={portfolio.id}
                    portfolio={portfolio}
                    blocked={blockedPortfolioIds.has(portfolio.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export default PortfoliosPage;
