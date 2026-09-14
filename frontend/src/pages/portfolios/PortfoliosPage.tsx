import { Link } from 'react-router-dom';
import { usePortfolios } from '../../api/portfolios';
import { BuildAIPortfolioCard } from './BuildAIPortfolioCard';
import type { Portfolio } from '../../types/api';

/** Turn a raw source/risk slug into a display label. */
function humanize(value: string | null): string {
  if (!value) return '—';
  return value.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function PortfolioRow({ portfolio }: { portfolio: Portfolio }) {
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3 font-semibold">
        <Link
          to={`/portfolios/${portfolio.id}`}
          className="text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          {portfolio.name}
        </Link>
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
    </tr>
  );
}

export function PortfoliosPage() {
  const { data, isPending, isError } = usePortfolios();
  const portfolios = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">
        Portfolios
      </h1>

      <BuildAIPortfolioCard />

      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-baseline gap-3 border-b border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">
            Stored portfolios
          </h2>
          {!isPending && !isError && total > 0 && (
            <span className="text-sm text-slate-500">
              {total} total
            </span>
          )}
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
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">Risk</th>
                  <th className="px-4 py-3 text-right">Holdings</th>
                  <th className="px-4 py-3 text-right">Max Alloc</th>
                  <th className="px-4 py-3">Created</th>
                </tr>
              </thead>
              <tbody>
                {portfolios.map((portfolio) => (
                  <PortfolioRow key={portfolio.id} portfolio={portfolio} />
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
