import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import {
  ASSET_PAGE_SIZES,
  DEFAULT_ASSET_DIRECTION,
  DEFAULT_ASSET_SORT,
  SECTORS,
  SUPPORTED_CATEGORIES,
  useAddAsset,
  useAssets,
  useDeleteAsset,
  type AssetPageSize,
} from '../../api/assets';
import { CategoryBadge, CATEGORY_STYLES } from '../../components/CategoryBadge';
import { SectorBadge, SECTOR_STYLES } from '../../components/SectorBadge';
import { RecommendAssetsCard } from './RecommendAssetsCard';
import type {
  Asset,
  AssetCategory,
  AssetSortDirection,
  AssetSortField,
  CriterionResult,
  Sector,
} from '../../types/api';

/** Format a USD monetary value compactly (e.g. $1.2B, $3.4M, $5.00). `null` → "—". */
function formatUsd(value: number | null): string {
  if (value === null || Number.isNaN(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(2)}`;
}

/** Format a year count (e.g. "7.3 yrs"). `null` → "—". */
function formatYears(value: number | null): string {
  if (value === null || Number.isNaN(value)) return '—';
  return `${value.toFixed(1)} yrs`;
}

/**
 * Human-readable label for a failed eligibility criterion, built from the
 * criterion's own `threshold`. Deriving the label from the actual threshold (not
 * a hardcoded string) keeps it correct across categories — crypto uses different
 * market-cap, turnover, and history floors than stocks, and no price criterion.
 */
function criterionLabel(c: CriterionResult): string {
  switch (c.name) {
    case 'price':
      return `Price > ${formatUsd(c.threshold)}`;
    case 'avg_daily_turnover':
      return `Avg daily turnover ≥ ${formatUsd(c.threshold)}`;
    case 'market_cap':
      return `Market cap > ${formatUsd(c.threshold)}`;
    case 'history':
      return `History ≥ ${c.threshold} ${c.threshold === 1 ? 'year' : 'years'}`;
    default:
      return c.name;
  }
}

/** Map an axios error from POST /assets to a user-facing message. */
function addErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    switch (error.response?.status) {
      case 409:
        return 'That asset already exists in your universe.';
      case 422: {
        // 422 now covers several distinct reasons (unknown ticker, unsupported
        // category, non-US listing that Alpaca can't trade). Prefer the API's
        // specific reason, falling back to the generic unknown-ticker message.
        const detail = error.response?.data?.detail;
        return typeof detail === 'string' && detail
          ? detail
          : 'Unknown ticker — the symbol could not be resolved.';
      }
      case 503:
        return 'The market-data provider is unavailable right now. Please try again later.';
      default:
        break;
    }
  }
  return 'Could not add the asset. Please try again.';
}

function EligibilityBadge({ asset }: { asset: Asset }) {
  const failed = asset.criteria_results.filter((c) => !c.passed);

  if (asset.is_eligible) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800">
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        Eligible
      </span>
    );
  }

  const failedLabels = failed.map(criterionLabel).join(', ');
  const tooltip = failedLabels ? `Failed: ${failedLabels}` : 'Not eligible';

  return (
    <span
      title={tooltip}
      className="inline-flex cursor-help items-center gap-1 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800"
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-red-500" />
      Not eligible
    </span>
  );
}

function AssetRow({ asset }: { asset: Asset }) {
  const deleteAsset = useDeleteAsset();

  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3 font-semibold">
        <Link
          to={`/assets/${asset.ticker}`}
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
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {formatUsd(asset.market_cap_usd)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {formatUsd(asset.avg_daily_turnover_usd)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {formatYears(asset.history_years)}
      </td>
      <td className="px-4 py-3">
        <EligibilityBadge asset={asset} />
      </td>
      <td className="px-4 py-3 text-right">
        <button
          type="button"
          onClick={() => deleteAsset.mutate(asset.id)}
          disabled={deleteAsset.isPending}
          className="rounded border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label={`Delete ${asset.ticker}`}
        >
          {deleteAsset.isPending ? 'Deleting…' : 'Delete'}
        </button>
      </td>
    </tr>
  );
}

/**
 * A sortable column header. Renders a `th` carrying `aria-sort` and a button
 * that requests sorting by `field`: clicking an inactive column sorts it
 * ascending; clicking the active column toggles direction.
 */
function SortableHeader({
  label,
  field,
  sort,
  direction,
  onSort,
  className,
}: {
  label: string;
  field: AssetSortField;
  sort: AssetSortField;
  direction: AssetSortDirection;
  onSort: (field: AssetSortField) => void;
  className?: string;
}) {
  const active = sort === field;
  const ariaSort = active
    ? direction === 'asc'
      ? 'ascending'
      : 'descending'
    : 'none';
  return (
    <th className={className} aria-sort={ariaSort}>
      <button
        type="button"
        onClick={() => onSort(field)}
        className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-slate-700 focus:outline-none focus:ring-1 focus:ring-emerald-500"
      >
        {label}
        <span aria-hidden="true" className="text-[0.6rem] leading-none">
          {active ? (direction === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  );
}

/** One selectable option in a multi-select dropdown. */
interface FilterOption<T extends string> {
  value: T;
  label: string;
}

/**
 * A multi-select dropdown filter. The trigger button shows `label` plus a count
 * badge when any options are selected; opening it reveals a checkbox per option.
 * An empty selection means "all". Clicking outside the panel closes it.
 */
function MultiSelectDropdown<T extends string>({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: readonly FilterOption<T>[];
  selected: T[];
  onToggle: (value: T) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const count = selected.length;

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="true"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
      >
        {label}
        {count > 0 && (
          <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-emerald-100 px-1.5 text-xs font-semibold text-emerald-800">
            {count}
          </span>
        )}
        <span
          aria-hidden="true"
          className="text-[0.6rem] leading-none text-slate-400"
        >
          ▼
        </span>
      </button>
      {open && (
        <fieldset className="absolute right-0 z-10 mt-1 flex max-h-72 w-56 flex-col gap-0.5 overflow-y-auto rounded border border-slate-200 bg-white p-2 shadow-lg">
          <legend className="sr-only">Filter by {label.toLowerCase()}</legend>
          {options.map((option) => (
            <label
              key={option.value}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm text-slate-700 hover:bg-slate-50"
            >
              <input
                type="checkbox"
                checked={selected.includes(option.value)}
                onChange={() => onToggle(option.value)}
                aria-label={`Filter by ${option.label}`}
                className="h-3.5 w-3.5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              {option.label}
            </label>
          ))}
        </fieldset>
      )}
    </div>
  );
}

/** Category filter options (value + display label), in the canonical order. */
const CATEGORY_OPTIONS: readonly FilterOption<AssetCategory>[] =
  SUPPORTED_CATEGORIES.map((value) => ({
    value,
    label: CATEGORY_STYLES[value].label,
  }));

/** Sector filter options (value + display label), in the canonical order. */
const SECTOR_OPTIONS: readonly FilterOption<Sector>[] = SECTORS.map((value) => ({
  value,
  label: SECTOR_STYLES[value].label,
}));

/** localStorage key holding the user's chosen assets-table page size. */
const PAGE_SIZE_STORAGE_KEY = 'cadence.assets.pageSize';

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

export function AssetsPage() {
  const addAsset = useAddAsset();

  const [ticker, setTicker] = useState('');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [pageSize, setPageSize] = useState<AssetPageSize>(readStoredPageSize);
  const [sort, setSort] = useState<AssetSortField>(DEFAULT_ASSET_SORT);
  const [direction, setDirection] =
    useState<AssetSortDirection>(DEFAULT_ASSET_DIRECTION);
  const [categories, setCategories] = useState<AssetCategory[]>([]);
  const [sectors, setSectors] = useState<Sector[]>([]);
  const universeHeadingRef = useRef<HTMLHeadingElement>(null);
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

  const focusUniverse = () => {
    const el = universeHeadingRef.current;
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el.focus();
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

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = ticker.trim();
    if (!trimmed) return;
    addAsset.mutate(trimmed, {
      onSuccess: () => setTicker(''),
    });
  };

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">Assets</h1>

      {/* Add / Recommend — two-column grid (stacks on mobile, equal height ≥ md) */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] md:items-stretch">
        {/* Add-asset section */}
        <div className="flex h-full flex-col rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">Add an asset</h2>
          <p className="mt-1 text-sm text-slate-500">
            Enter a ticker symbol to fetch its market data and evaluate eligibility.
          </p>
          <form onSubmit={handleAdd} className="mt-4 flex items-start gap-2">
            <div className="flex-1">
              <label htmlFor="ticker" className="sr-only">
                Ticker symbol
              </label>
              <input
                id="ticker"
                type="text"
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                placeholder="e.g. AAPL"
                autoComplete="off"
                className="w-full rounded border border-slate-300 px-3 py-2 text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            <button
              type="submit"
              disabled={addAsset.isPending || !ticker.trim()}
              className="rounded bg-emerald-500 px-4 py-2 font-medium text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {addAsset.isPending ? 'Adding…' : 'Add'}
            </button>
          </form>
          {addAsset.isError && (
            <p
              role="alert"
              className="mt-3 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
            >
              {addErrorMessage(addAsset.error)}
            </p>
          )}
          <p className="mt-auto pt-6 text-xs text-slate-500">
            Tip: add tickers one at a time, or let the recommender suggest and add a
            batch for you.
          </p>
        </div>

        {/* Recommend-assets section */}
        <RecommendAssetsCard onViewUniverse={focusUniverse} />
      </div>

      {/* List section */}
      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-baseline gap-3">
            <h2
              ref={universeHeadingRef}
              tabIndex={-1}
              className="text-lg font-semibold text-slate-900 focus:outline-none"
            >
              Asset universe
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
                Search assets
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
            Loading assets…
          </p>
        )}

        {isError && (
          <div
            role="alert"
            className="m-4 rounded border border-red-300 bg-red-50 p-4 text-red-800"
          >
            <p className="font-semibold">Could not load assets</p>
            <p className="mt-1 text-sm">Please try again later.</p>
          </div>
        )}

        {!isPending && !isError && total === 0 && !isFiltering && (
          <p className="p-6 text-slate-500">
            No assets yet. Add one above to get started.
          </p>
        )}

        {!isPending && !isError && total === 0 && isFiltering && (
          <p className="p-6 text-slate-500">
            No assets match your search and filters.
          </p>
        )}

        {!isPending && !isError && assets.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-collapse text-sm">
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
                  <th className="px-4 py-3 text-right">Market Cap ($)</th>
                  <th className="px-4 py-3 text-right">Avg Daily Turnover ($)</th>
                  <th className="px-4 py-3 text-right">History</th>
                  <th className="px-4 py-3">Eligibility</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => (
                  <AssetRow key={asset.id} asset={asset} />
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

export default AssetsPage;
