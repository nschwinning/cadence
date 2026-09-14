import { Link, useParams } from 'react-router-dom';
import axios from 'axios';
import { useAssetDetail } from '../../api/assets';
import { CategoryBadge } from '../../components/CategoryBadge';
import { SectorBadge } from '../../components/SectorBadge';
import type { AssetDetail, AssetDetailHistoryPoint } from '../../types/api';

/**
 * Format a monetary value in the asset's native currency using the browser
 * locale. Falls back to a plain number + code if the currency is not recognised
 * by `Intl`. `null` → "—".
 */
function formatPrice(value: number | null, currency: string): string {
  if (value === null || Number.isNaN(value)) return '—';
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
    }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}

/** The daily change vs the previous close, as an absolute amount and a percentage. */
interface DailyChange {
  absolute: number;
  percent: number;
  direction: 'up' | 'down' | 'flat';
}

function computeChange(
  current: number | null,
  previous: number | null,
): DailyChange | null {
  if (
    current === null ||
    previous === null ||
    Number.isNaN(current) ||
    Number.isNaN(previous)
  ) {
    return null;
  }
  const absolute = current - previous;
  const percent = previous !== 0 ? (absolute / previous) * 100 : 0;
  const direction = absolute > 0 ? 'up' : absolute < 0 ? 'down' : 'flat';
  return { absolute, percent, direction };
}

const CHANGE_TEXT_CLASS: Record<DailyChange['direction'], string> = {
  up: 'text-emerald-700',
  down: 'text-red-700',
  flat: 'text-slate-600',
};

const CHANGE_SIGN: Record<DailyChange['direction'], string> = {
  up: '+',
  down: '−',
  flat: '',
};

const TREND_STROKE: Record<DailyChange['direction'], string> = {
  up: '#059669',
  down: '#dc2626',
  flat: '#64748b',
};

/**
 * A lightweight inline SVG sparkline of the price history. Kept dependency-free
 * (utility-only styling, native SVG) to match the app's conventions.
 */
function PriceSparkline({
  history,
  trend,
}: {
  history: AssetDetailHistoryPoint[];
  trend: DailyChange['direction'];
}) {
  if (history.length < 2) {
    return (
      <div className="flex h-40 items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 text-sm text-slate-400">
        Not enough price history to chart.
      </div>
    );
  }

  const width = 800;
  const height = 160;
  const pad = 8;
  const closes = history.map((p) => p.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;

  const points = history.map((p, i) => {
    const x = pad + (i / (history.length - 1)) * (width - 2 * pad);
    const y = pad + (1 - (p.close - min) / span) * (height - 2 * pad);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-40 w-full"
      role="img"
      aria-label={`Price history over the last ${history.length} data points`}
    >
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={TREND_STROKE[trend]}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function BackToAssetsLink() {
  return (
    <Link
      to="/assets"
      className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700 hover:text-emerald-800 hover:underline"
    >
      <span aria-hidden="true">←</span> Back to assets
    </Link>
  );
}

/** Two-column core-facts item. */
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

function DetailView({ detail }: { detail: AssetDetail }) {
  const change = computeChange(detail.current_price, detail.previous_close);
  const trend = change?.direction ?? 'flat';

  return (
    <section className="flex flex-col gap-6">
      <BackToAssetsLink />

      {/* Header */}
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {detail.name ?? detail.ticker}
          </h1>
          <CategoryBadge category={detail.category} />
          <SectorBadge sector={detail.sector} />
        </div>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-500">
          <span className="font-semibold text-slate-700">{detail.ticker}</span>
          {detail.exchange && (
            <>
              <span aria-hidden="true">·</span>
              <span>{detail.exchange}</span>
            </>
          )}
          <span aria-hidden="true">·</span>
          <span>{detail.currency}</span>
        </p>
      </header>

      {/* Price + change */}
      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="text-3xl font-bold tabular-nums text-slate-900">
            {formatPrice(detail.current_price, detail.currency)}
          </span>
          {change ? (
            <span
              className={`text-sm font-semibold tabular-nums ${CHANGE_TEXT_CLASS[change.direction]}`}
            >
              {CHANGE_SIGN[change.direction]}
              {formatPrice(Math.abs(change.absolute), detail.currency)} (
              {CHANGE_SIGN[change.direction]}
              {Math.abs(change.percent).toFixed(2)}%)
            </span>
          ) : (
            <span className="text-sm text-slate-500">Change unavailable</span>
          )}
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Prices in {detail.currency}, as of {detail.snapshot_date}.
        </p>

        <div className="mt-6">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">
            Price history
          </h2>
          <PriceSparkline history={detail.price_history} trend={trend} />
        </div>
      </div>

      {/* Core facts */}
      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Core facts</h2>
        <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Fact label="Name" value={detail.name ?? '—'} />
          <Fact label="Ticker" value={detail.ticker} />
          <Fact label="Exchange" value={detail.exchange ?? '—'} />
          <Fact label="Currency" value={detail.currency} />
        </dl>
        {detail.short_description && (
          <p className="mt-6 max-w-3xl text-sm leading-relaxed text-slate-700">
            {detail.short_description}
          </p>
        )}
      </div>

      {/* Company information */}
      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">
          Company information
        </h2>
        <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Fact label="Country" value={detail.country ?? '—'} />
          <Fact label="City" value={detail.city ?? '—'} />
          <Fact
            label="Employees"
            value={
              detail.employees !== null
                ? detail.employees.toLocaleString()
                : '—'
            }
          />
          <Fact
            label="Volume"
            value={detail.volume !== null ? detail.volume.toLocaleString() : '—'}
          />
          <Fact
            label="Avg volume"
            value={
              detail.avg_volume !== null
                ? detail.avg_volume.toLocaleString()
                : '—'
            }
          />
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Website
            </dt>
            <dd className="text-sm text-slate-900">
              {detail.website ? (
                <a
                  href={detail.website}
                  target="_blank"
                  rel="noreferrer"
                  className="text-emerald-700 hover:text-emerald-800 hover:underline"
                >
                  {detail.website}
                </a>
              ) : (
                '—'
              )}
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

export function AssetDetailPage() {
  const { ticker = '' } = useParams<{ ticker: string }>();
  const { data, isPending, isError, error, refetch, isFetching } =
    useAssetDetail(ticker);

  if (isPending) {
    return (
      <section className="flex flex-col gap-6">
        <BackToAssetsLink />
        <p role="status" aria-live="polite" className="text-slate-500">
          Loading asset details…
        </p>
        <div
          aria-hidden="true"
          className="h-56 w-full animate-pulse rounded-lg border border-slate-200 bg-slate-100"
        />
      </section>
    );
  }

  if (isError) {
    const notFound = axios.isAxiosError(error) && error.response?.status === 404;

    if (notFound) {
      return (
        <section className="flex flex-col gap-6">
          <BackToAssetsLink />
          <div
            role="alert"
            className="max-w-xl rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
          >
            <h1 className="text-xl font-bold text-slate-900">Asset not found</h1>
            <p className="mt-2 text-sm text-slate-600">
              <span className="font-semibold">{ticker}</span> is not in your
              universe. Add it from the assets page to view its details.
            </p>
            <div className="mt-4">
              <Link
                to="/assets"
                className="inline-flex rounded bg-emerald-500 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600"
              >
                Go to assets
              </Link>
            </div>
          </div>
        </section>
      );
    }

    return (
      <section className="flex flex-col gap-6">
        <BackToAssetsLink />
        <div
          role="alert"
          className="max-w-xl rounded-lg border border-red-300 bg-red-50 p-6 shadow-sm"
        >
          <h1 className="text-xl font-bold text-red-800">
            Could not load details right now
          </h1>
          <p className="mt-2 text-sm text-red-800">
            The market data for{' '}
            <span className="font-semibold">{ticker}</span> is temporarily
            unavailable. Please try again in a moment.
          </p>
          <div className="mt-4">
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
              className="inline-flex rounded bg-emerald-500 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isFetching ? 'Retrying…' : 'Retry'}
            </button>
          </div>
        </div>
      </section>
    );
  }

  return <DetailView detail={data} />;
}

export default AssetDetailPage;
