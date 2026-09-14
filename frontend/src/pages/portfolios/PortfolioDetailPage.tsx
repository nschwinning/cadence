import { Link, useParams } from 'react-router-dom';
import axios from 'axios';
import { usePortfolio } from '../../api/portfolios';
import type { Portfolio } from '../../types/api';

/** Turn a raw source/risk slug into a display label. */
function humanize(value: string | null): string {
  if (!value) return '—';
  return value.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function BackToPortfoliosLink() {
  return (
    <Link
      to="/portfolios"
      className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700 hover:text-emerald-800 hover:underline"
    >
      <span aria-hidden="true">←</span> Back to portfolios
    </Link>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="text-sm text-slate-900">{value}</dd>
    </div>
  );
}

function DetailView({ portfolio }: { portfolio: Portfolio }) {
  return (
    <section className="flex flex-col gap-6">
      <BackToPortfoliosLink />

      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          {portfolio.name}
        </h1>
        {portfolio.description && (
          <p className="max-w-3xl text-sm text-slate-600">
            {portfolio.description}
          </p>
        )}
      </header>

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Overview</h2>
        <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Fact label="Source" value={humanize(portfolio.source)} />
          <Fact label="Risk profile" value={humanize(portfolio.risk_profile)} />
          <Fact
            label="Max allocation"
            value={`${(portfolio.max_allocation_pct * 100).toFixed(0)}%`}
          />
          <Fact label="Holdings" value={String(portfolio.stocks.length)} />
          <Fact
            label="Created"
            value={new Date(portfolio.created_at).toLocaleString()}
          />
          <Fact label="Source run" value={portfolio.source_run_id ?? '—'} />
        </dl>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Holdings</h2>
        {portfolio.stocks.length === 0 ? (
          <p className="mt-3 text-sm text-slate-400">No holdings.</p>
        ) : (
          <ul className="mt-4 flex flex-wrap gap-2">
            {portfolio.stocks.map((ticker) => (
              <li key={ticker}>
                <Link
                  to={`/assets/${ticker}`}
                  className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-200"
                >
                  {ticker}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export function PortfolioDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const { data, isPending, isError, error } = usePortfolio(id);

  if (isPending) {
    return (
      <section className="flex flex-col gap-6">
        <BackToPortfoliosLink />
        <p role="status" aria-live="polite" className="text-slate-500">
          Loading portfolio…
        </p>
      </section>
    );
  }

  if (isError) {
    const notFound = axios.isAxiosError(error) && error.response?.status === 404;
    return (
      <section className="flex flex-col gap-6">
        <BackToPortfoliosLink />
        <div
          role="alert"
          className="max-w-xl rounded-lg border border-red-300 bg-red-50 p-6 shadow-sm"
        >
          <h1 className="text-xl font-bold text-red-800">
            {notFound ? 'Portfolio not found' : 'Could not load portfolio'}
          </h1>
          <p className="mt-2 text-sm text-red-800">
            {notFound
              ? 'This portfolio does not exist or has been removed.'
              : 'Please try again in a moment.'}
          </p>
        </div>
      </section>
    );
  }

  return <DetailView portfolio={data} />;
}

export default PortfolioDetailPage;
