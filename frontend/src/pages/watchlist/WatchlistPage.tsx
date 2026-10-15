import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { assetKeys, useWatchlist } from '../../api/assets';
import {
  isTerminalPhase,
  useCreateRecommendationRun,
  useRecommendationRun,
} from '../../api/recommendations';
import type {
  Asset,
  AssetFundamentals,
  FundamentalsFigure,
  RecommendationCandidateResult,
  RunPhase,
} from '../../types/api';

/** Human label per in-flight/terminal phase, for the live status badge. */
const PHASE_LABELS: Record<RunPhase, string> = {
  queued: 'Queued',
  searching: 'Searching',
  validating: 'Validating',
  completed: 'Completed',
  failed: 'Failed',
};

/** Order + labels for the known EDGAR figures we render. */
const FIGURE_ROWS: { key: string; label: string; marginOf?: 'revenue' }[] = [
  { key: 'revenue', label: 'Revenue' },
  { key: 'gross_profit', label: 'Gross profit', marginOf: 'revenue' },
  { key: 'operating_income', label: 'Operating income', marginOf: 'revenue' },
  { key: 'net_income', label: 'Net income', marginOf: 'revenue' },
  { key: 'operating_cash_flow', label: 'Operating cash flow' },
  { key: 'eps_basic', label: 'EPS (basic)' },
  { key: 'eps_diluted', label: 'EPS (diluted)' },
];

/** Keys rendered as per-share currency rather than compact large numbers. */
const PER_SHARE_KEYS = new Set(['eps_basic', 'eps_diluted']);

/** Format a large USD figure compactly (e.g. `$1.2B`, `-$340.0M`). */
function formatCompactUsd(value: number): string {
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  const units: [number, string][] = [
    [1e12, 'T'],
    [1e9, 'B'],
    [1e6, 'M'],
    [1e3, 'K'],
  ];
  for (const [scale, suffix] of units) {
    if (abs >= scale) return `${sign}$${(abs / scale).toFixed(1)}${suffix}`;
  }
  return `${sign}$${abs.toFixed(0)}`;
}

/** Format a per-share figure (EPS) with two decimals. */
function formatPerShare(value: number): string {
  const sign = value < 0 ? '-' : '';
  return `${sign}$${Math.abs(value).toFixed(2)}`;
}

/** Format a single figure's value for display, by key. */
function formatFigureValue(key: string, figure: FundamentalsFigure): string {
  return PER_SHARE_KEYS.has(key)
    ? formatPerShare(figure.value)
    : formatCompactUsd(figure.value);
}

/** A readable company-details value, flattening arrays/objects to text. */
function detailText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) {
    const joined = value.filter((v) => v != null).join(', ');
    return joined.length > 0 ? joined : null;
  }
  if (typeof value === 'object') return null;
  const text = String(value);
  return text.length > 0 ? text : null;
}

/** The company details worth surfacing, in display order (label → doc key). */
const DETAIL_ROWS: { key: string; label: string }[] = [
  { key: 'sicDescription', label: 'Industry' },
  { key: 'exchanges', label: 'Exchanges' },
  { key: 'sic', label: 'SIC code' },
];

/** Pick the best available company name from the fundamentals document. */
function companyName(fundamentals: AssetFundamentals): string | null {
  const details = fundamentals.document.company_details;
  if (details && typeof details === 'object') {
    const name =
      detailText((details as Record<string, unknown>).name) ??
      detailText((details as Record<string, unknown>).entity_name);
    if (name) return name;
  }
  return null;
}

/** The fundamentals detail block for one watchlist entry. */
function FundamentalsPanel({
  fundamentals,
}: {
  fundamentals: AssetFundamentals;
}) {
  if (fundamentals.status === 'unavailable') {
    return (
      <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
        Fundamentals unavailable — SEC EDGAR had no filings for this ticker or was
        unreachable when it was added.
      </p>
    );
  }

  const figures = fundamentals.document.figures ?? {};
  const revenue = figures.revenue?.value;
  const rows = FIGURE_ROWS.filter((row) => figures[row.key] !== undefined);
  const details = (fundamentals.document.company_details ?? {}) as Record<
    string,
    unknown
  >;
  const detailRows = DETAIL_ROWS.map((row) => ({
    label: row.label,
    text: detailText(details[row.key]),
  })).filter((row) => row.text !== null);

  return (
    <div className="flex flex-col gap-3">
      {fundamentals.status === 'partial' && (
        <p className="text-xs font-medium text-amber-700">
          Partial fundamentals — some figures were missing from EDGAR.
        </p>
      )}

      {rows.length > 0 ? (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <th className="py-1 pr-4">Figure</th>
              <th className="py-1 pr-4 text-right">Latest annual</th>
              <th className="py-1 text-right">Margin</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const figure = figures[row.key]!;
              const margin =
                row.marginOf === 'revenue' &&
                typeof revenue === 'number' &&
                revenue !== 0
                  ? (figure.value / revenue) * 100
                  : null;
              return (
                <tr key={row.key} className="border-t border-slate-100">
                  <td className="py-1 pr-4 text-slate-700">{row.label}</td>
                  <td className="py-1 pr-4 text-right font-medium tabular-nums text-slate-900">
                    {formatFigureValue(row.key, figure)}
                    {figure.period_end && (
                      <span className="ml-1 text-xs font-normal text-slate-400">
                        ({figure.period_end})
                      </span>
                    )}
                  </td>
                  <td className="py-1 text-right tabular-nums text-slate-600">
                    {margin !== null ? `${margin.toFixed(1)}%` : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-slate-500">
          No figures were reported for this company.
        </p>
      )}

      {detailRows.length > 0 && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
          {detailRows.map((row) => (
            <div key={row.label} className="contents">
              <dt className="text-slate-500">{row.label}</dt>
              <dd className="text-slate-700">{row.text}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

/** A single watchlist entry card: ticker + name, eligibility, fundamentals. */
function WatchlistEntry({ asset }: { asset: Asset }) {
  const name =
    asset.name ??
    (asset.fundamentals ? companyName(asset.fundamentals) : null);
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-lg font-bold tabular-nums text-slate-900">
          {asset.ticker}
        </span>
        {name && <span className="text-sm text-slate-500">{name}</span>}
        {!asset.is_eligible && (
          <span className="ml-auto inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800">
            Below universe bar
          </span>
        )}
      </div>

      <div className="mt-4">
        {asset.fundamentals ? (
          <FundamentalsPanel fundamentals={asset.fundamentals} />
        ) : (
          <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
            No fundamentals on record for this entry.
          </p>
        )}
      </div>
    </li>
  );
}

/** Derived rollup counts over a run's candidate results. */
function rollup(results: RecommendationCandidateResult[]) {
  let added = 0;
  let skipped = 0;
  let errored = 0;
  for (const r of results) {
    if (r.outcome === 'added') added += 1;
    else if (r.outcome === 'error') errored += 1;
    else skipped += 1;
  }
  return { added, skipped, errored };
}

/** Card that triggers a watchlist-targeted recommendation run and polls it. */
function WatchlistRecommendCard({ onAdded }: { onAdded: () => void }) {
  const createRun = useCreateRecommendationRun();
  const [count, setCount] = useState('3');
  const [runId, setRunId] = useState<number | null>(null);

  const runQuery = useRecommendationRun(runId);
  const run = runQuery.data;
  const phase = run?.status;
  const terminal = phase ? isTerminalPhase(phase) : false;
  const running = runId !== null && !terminal;

  const countValue = Number.parseInt(count, 10);
  const countValid = Number.isFinite(countValue) && countValue >= 1;

  // One-shot: refresh the watchlist once when a run completes.
  const notifiedRunId = useRef<number | null>(null);
  useEffect(() => {
    if (
      runId !== null &&
      phase === 'completed' &&
      notifiedRunId.current !== runId
    ) {
      notifiedRunId.current = runId;
      onAdded();
    }
  }, [runId, phase, onAdded]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!countValid) return;
    createRun.mutate(
      { count: countValue, categories: ['stock'], target: 'watchlist' },
      { onSuccess: (created) => setRunId(created.id) },
    );
  };

  const reset = () => {
    setRunId(null);
    createRun.reset();
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">
        Discover emerging companies
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Let Cadence&apos;s AI surface emerging stocks from promising sectors and
        add them to your watchlist with their SEC EDGAR fundamentals — research
        only, never traded.
      </p>

      {runId === null && (
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
          <div>
            <label
              htmlFor="watchlist-count"
              className="block text-sm font-medium text-slate-700"
            >
              How many to add (up to)
            </label>
            <div className="mt-1 flex items-center gap-3">
              <input
                id="watchlist-count"
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                value={count}
                onChange={(e) => setCount(e.target.value)}
                onBlur={() => {
                  if (!countValid) setCount('1');
                }}
                className="w-28 rounded border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              <span className="text-xs text-slate-500">
                Emerging stocks only.
              </span>
            </div>
          </div>

          {createRun.isError && (
            <p
              role="alert"
              className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
            >
              Could not start the watchlist run. Please try again.
            </p>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!countValid || createRun.isPending}
              aria-busy={createRun.isPending}
              className="rounded bg-emerald-500 px-4 py-2 font-medium text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {createRun.isPending ? 'Discover…' : 'Discover'}
            </button>
          </div>
        </form>
      )}

      {running && (
        <div
          role="status"
          aria-live="polite"
          className="mt-4 flex items-center gap-2 text-sm text-slate-600"
        >
          <span
            aria-hidden="true"
            className="h-3.5 w-3.5 rounded-full border-2 border-slate-300 border-t-emerald-500 motion-safe:animate-spin"
          />
          <span>Discovering… phase: {PHASE_LABELS[phase ?? 'queued']}</span>
        </div>
      )}

      {runId !== null && phase === 'completed' && run && (
        <div className="mt-4 flex flex-col gap-3">
          <div
            role="alert"
            className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
          >
            {(() => {
              const { added, skipped, errored } = rollup(run.results);
              const word = added === 1 ? 'company' : 'companies';
              return added > 0
                ? `Added ${added} ${word} to your watchlist. Skipped ${skipped}, ${errored} error(s).`
                : `No new companies were added. Skipped ${skipped}, ${errored} error(s).`;
            })()}
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={reset}
              className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Discover more
            </button>
          </div>
        </div>
      )}

      {runId !== null && phase === 'failed' && run && (
        <div className="mt-4 flex flex-col gap-3">
          <div
            role="alert"
            className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
          >
            <p className="font-semibold">Watchlist run failed.</p>
            <p className="mt-1 whitespace-pre-wrap break-words">
              {run.error && run.error.trim().length > 0
                ? run.error
                : 'An unknown error occurred.'}
            </p>
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={reset}
              className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Try again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function WatchlistPage() {
  const queryClient = useQueryClient();
  const { data, isPending, isError } = useWatchlist();
  const entries = data ?? [];

  const refreshWatchlist = () => {
    queryClient.invalidateQueries({ queryKey: assetKeys.watchlist });
  };

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">
        Watchlist
      </h1>

      <WatchlistRecommendCard onAdded={refreshWatchlist} />

      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold text-slate-900">
          Watched companies
          {!isPending && !isError && entries.length > 0 && (
            <span className="ml-2 text-sm font-normal text-slate-500">
              {entries.length} total
            </span>
          )}
        </h2>

        {isPending && (
          <p role="status" aria-live="polite" className="text-slate-500">
            Loading watchlist…
          </p>
        )}

        {isError && (
          <div
            role="alert"
            className="rounded border border-red-300 bg-red-50 p-4 text-red-800"
          >
            <p className="font-semibold">Could not load the watchlist</p>
            <p className="mt-1 text-sm">Please try again later.</p>
          </div>
        )}

        {!isPending && !isError && entries.length === 0 && (
          <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-6 text-slate-500">
            Your watchlist is empty. Use “Discover emerging companies” above to
            add research candidates.
          </p>
        )}

        {!isPending && !isError && entries.length > 0 && (
          <ul className="flex flex-col gap-4">
            {entries.map((asset) => (
              <WatchlistEntry key={asset.id} asset={asset} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default WatchlistPage;
