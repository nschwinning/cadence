import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  ASSET_PAGE_SIZES,
  DEFAULT_ASSET_DIRECTION,
  DEFAULT_ASSET_SORT,
  assetKeys,
  useAssets,
  type AssetPageSize,
} from '../../api/assets';
import {
  CATEGORY_OPTIONS,
  MultiSelectDropdown,
  SECTOR_OPTIONS,
  SortableHeader,
} from '../assets/AssetsPage';
import { CategoryBadge } from '../../components/CategoryBadge';
import { SectorBadge } from '../../components/SectorBadge';
import {
  isTerminalPhase,
  useCreateRecommendationRun,
  useRecommendationRun,
} from '../../api/recommendations';
import type {
  Asset,
  AssetCategory,
  AssetSortDirection,
  AssetSortField,
  RecommendationCandidateResult,
  RunPhase,
  Sector,
} from '../../types/api';

/** Human label per in-flight/terminal phase, for the live status badge. */
const PHASE_LABELS: Record<RunPhase, string> = {
  queued: 'Queued',
  searching: 'Searching',
  validating: 'Validating',
  completed: 'Completed',
  failed: 'Failed',
};

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

/** A single watchlist table row: ticker (linked to detail), name, badges. */
function WatchlistRow({ asset }: { asset: Asset }) {
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3 font-semibold">
        <Link
          to={`/assets/${asset.ticker}`}
          state={{ from: 'watchlist' }}
          className="text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          {asset.ticker}
        </Link>
      </td>
      <td className="px-4 py-3 text-slate-700">{asset.name ?? '—'}</td>
      <td className="px-4 py-3">
        <CategoryBadge category={asset.category} />
      </td>
      <td className="px-4 py-3">
        <SectorBadge sector={asset.sector} />
      </td>
      <td className="px-4 py-3">
        {asset.is_eligible ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800">
            <span
              aria-hidden="true"
              className="h-1.5 w-1.5 rounded-full bg-emerald-500"
            />
            Meets universe bar
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800">
            <span
              aria-hidden="true"
              className="h-1.5 w-1.5 rounded-full bg-amber-500"
            />
            Below universe bar
          </span>
        )}
      </td>
    </tr>
  );
}

/** localStorage key holding the user's chosen watchlist-table page size. */
const PAGE_SIZE_STORAGE_KEY = 'cadence.watchlist.pageSize';

/** Read a valid persisted page size, falling back to the smallest (20). */
function readStoredPageSize(): AssetPageSize {
  try {
    const raw = window.localStorage.getItem(PAGE_SIZE_STORAGE_KEY);
    const parsed = raw === null ? NaN : Number(raw);
    if ((ASSET_PAGE_SIZES as readonly number[]).includes(parsed)) {
      return parsed as AssetPageSize;
    }
  } catch {
    // Ignore storage access errors (private mode, disabled storage).
  }
  return ASSET_PAGE_SIZES[0];
}

export function WatchlistPage() {
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [pageSize, setPageSize] = useState<AssetPageSize>(readStoredPageSize);
  const [sort, setSort] = useState<AssetSortField>(DEFAULT_ASSET_SORT);
  const [direction, setDirection] =
    useState<AssetSortDirection>(DEFAULT_ASSET_DIRECTION);
  const [categories, setCategories] = useState<AssetCategory[]>([]);
  const [sectors, setSectors] = useState<Sector[]>([]);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Debounce the search box so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedSearch(search), 300);
    return () => window.clearTimeout(id);
  }, [search]);

  const {
    data,
    isPending,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useAssets({
    pageSize,
    search: debouncedSearch,
    sort,
    direction,
    categories,
    sectors,
    membership: 'watchlist',
  });

  const handleSort = (field: AssetSortField) => {
    if (sort === field) {
      setDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSort(field);
      setDirection('asc');
    }
  };

  const handleCategoryToggle = (category: AssetCategory) => {
    setCategories((prev) =>
      prev.includes(category)
        ? prev.filter((c) => c !== category)
        : [...prev, category],
    );
  };

  const handleSectorToggle = (sector: Sector) => {
    setSectors((prev) =>
      prev.includes(sector)
        ? prev.filter((s) => s !== sector)
        : [...prev, sector],
    );
  };

  // Flatten the loaded pages, de-duping by id.
  const assets = useMemo(() => {
    const seen = new Set<number>();
    const rows: Asset[] = [];
    for (const page of data?.pages ?? []) {
      for (const asset of page.items) {
        if (!seen.has(asset.id)) {
          seen.add(asset.id);
          rows.push(asset);
        }
      }
    }
    return rows;
  }, [data]);

  const total = data?.pages[0]?.total ?? 0;
  const isSearching = debouncedSearch.trim().length > 0;
  const isFiltering =
    isSearching || categories.length > 0 || sectors.length > 0;

  const refreshWatchlist = () => {
    // The watchlist is listed via the shared assets query path, so invalidate
    // all assets lists to pick up newly added watchlist entries.
    queryClient.invalidateQueries({ queryKey: assetKeys.all });
  };

  const handlePageSizeChange = (next: AssetPageSize) => {
    setPageSize(next);
    try {
      window.localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(next));
    } catch {
      // Ignore storage write errors; the in-memory choice still applies.
    }
  };

  // Infinite scroll: load the next page when the sentinel scrolls into view.
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !hasNextPage) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
        void fetchNextPage();
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, assets.length]);

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">
        Watchlist
      </h1>

      <WatchlistRecommendCard onAdded={refreshWatchlist} />

      {/* List section */}
      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-baseline gap-3">
            <h2 className="text-lg font-semibold text-slate-900">
              Watched companies
            </h2>
            {!isPending && !isError && total > 0 && (
              <span className="text-sm text-slate-500" aria-live="polite">
                Showing {assets.length} of {total}
              </span>
            )}
          </div>
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
            <div className="flex items-center gap-2">
              <label htmlFor="page-size" className="text-sm text-slate-500">
                Per page
              </label>
              <select
                id="page-size"
                value={pageSize}
                onChange={(e) =>
                  handlePageSizeChange(Number(e.target.value) as AssetPageSize)
                }
                className="rounded border border-slate-300 px-2 py-2 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {ASSET_PAGE_SIZES.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </div>
            <div className="w-full sm:w-72">
              <label htmlFor="search" className="sr-only">
                Search watchlist
              </label>
              <input
                id="search"
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by ticker or name…"
                className="w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            <MultiSelectDropdown
              label="Categories"
              options={CATEGORY_OPTIONS}
              selected={categories}
              onToggle={handleCategoryToggle}
            />
            <MultiSelectDropdown
              label="Sectors"
              options={SECTOR_OPTIONS}
              selected={sectors}
              onToggle={handleSectorToggle}
            />
          </div>
        </div>

        {isPending && (
          <p role="status" aria-live="polite" className="p-6 text-slate-500">
            Loading watchlist…
          </p>
        )}

        {isError && (
          <div
            role="alert"
            className="m-4 rounded border border-red-300 bg-red-50 p-4 text-red-800"
          >
            <p className="font-semibold">Could not load the watchlist</p>
            <p className="mt-1 text-sm">Please try again later.</p>
          </div>
        )}

        {!isPending && !isError && total === 0 && !isFiltering && (
          <p className="p-6 text-slate-500">
            Your watchlist is empty. Use “Discover emerging companies” above to
            add research candidates.
          </p>
        )}

        {!isPending && !isError && total === 0 && isFiltering && (
          <p className="p-6 text-slate-500">
            No watchlist companies match your search and filters.
          </p>
        )}

        {!isPending && !isError && assets.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <SortableHeader
                    label="Ticker"
                    field="ticker"
                    sort={sort}
                    direction={direction}
                    onSort={handleSort}
                    className="px-4 py-3"
                  />
                  <SortableHeader
                    label="Name"
                    field="name"
                    sort={sort}
                    direction={direction}
                    onSort={handleSort}
                    className="px-4 py-3"
                  />
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3">Sector</th>
                  <th className="px-4 py-3">Universe bar</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => (
                  <WatchlistRow key={asset.id} asset={asset} />
                ))}
              </tbody>
            </table>

            {/* Infinite-scroll sentinel: intersecting triggers the next page. */}
            <div ref={sentinelRef} aria-hidden="true" className="h-px" />

            {isFetchingNextPage && (
              <p
                role="status"
                aria-live="polite"
                className="p-4 text-center text-sm text-slate-500"
              >
                Loading more…
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

export default WatchlistPage;
