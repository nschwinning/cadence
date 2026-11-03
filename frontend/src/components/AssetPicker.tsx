import { useId, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listAssets } from '../api/assets';
import type { Asset } from '../types/api';

/**
 * A universe-backed, searchable multi-select for eligible universe equities. It
 * queries `listAssets({ search, membership: 'universe', category: 'stock' })` for
 * typeahead matches and lets the user build a set of tickers by picking from the
 * results — there is no free-text entry, so only real universe stocks can be
 * selected (mirroring the backend's membership validation). A "whole universe"
 * toggle selects every eligible universe equity at creation; while it is on the
 * individual picker is disabled because the set is resolved server-side.
 */
export function AssetPicker({
  selected,
  onChange,
  wholeUniverse,
  onWholeUniverseChange,
}: {
  /** Currently selected tickers (uppercase). */
  selected: string[];
  onChange: (tickers: string[]) => void;
  /** Whether "whole universe" is chosen (individual picks ignored when true). */
  wholeUniverse: boolean;
  onWholeUniverseChange: (value: boolean) => void;
}) {
  const [search, setSearch] = useState('');
  const listboxId = useId();
  const trimmed = search.trim();

  // Typeahead over the eligible universe stocks. Disabled while "whole universe"
  // is on (the set is resolved on the backend) and until a search term exists.
  const { data, isFetching } = useQuery({
    queryKey: ['asset-picker', trimmed],
    queryFn: () =>
      listAssets({
        limit: 20,
        offset: 0,
        search: trimmed,
        sort: 'ticker',
        direction: 'asc',
        categories: ['stock'],
        sectors: [],
        membership: 'universe',
      }),
    enabled: !wholeUniverse && trimmed.length > 0,
  });

  const selectedSet = useMemo(() => new Set(selected), [selected]);
  // Hide already-selected tickers from the result list.
  const results: Asset[] = (data?.items ?? []).filter(
    (a) => !selectedSet.has(a.ticker),
  );

  const add = (ticker: string) => {
    if (selectedSet.has(ticker)) return;
    onChange([...selected, ticker]);
    setSearch('');
  };

  const remove = (ticker: string) => {
    onChange(selected.filter((t) => t !== ticker));
  };

  return (
    <div className="flex flex-col gap-2">
      <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
        <input
          type="checkbox"
          checked={wholeUniverse}
          onChange={(e) => onWholeUniverseChange(e.target.checked)}
          className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
        />
        Trade the whole eligible universe
      </label>

      {wholeUniverse ? (
        <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          The bot will trade every eligible universe equity, resolved at creation.
        </p>
      ) : (
        <>
          <div>
            <input
              type="text"
              role="combobox"
              aria-expanded={results.length > 0}
              aria-controls={listboxId}
              aria-autocomplete="list"
              aria-label="Search universe equities"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tickers, e.g. AAPL"
              className="mt-1 w-full rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
            {trimmed.length > 0 && (
              <ul
                id={listboxId}
                role="listbox"
                aria-label="Matching universe equities"
                className="mt-1 max-h-48 overflow-y-auto rounded border border-slate-200 bg-white text-sm shadow-sm"
              >
                {isFetching && results.length === 0 && (
                  <li className="px-3 py-2 text-slate-400">Searching…</li>
                )}
                {!isFetching && results.length === 0 && (
                  <li className="px-3 py-2 text-slate-400">
                    No eligible universe equities match.
                  </li>
                )}
                {results.map((a) => (
                  <li key={a.id} role="option" aria-selected={false}>
                    <button
                      type="button"
                      onClick={() => add(a.ticker)}
                      className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                    >
                      <span className="font-semibold text-slate-900">
                        {a.ticker}
                      </span>
                      <span className="truncate text-xs text-slate-500">
                        {a.name ?? ''}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex flex-wrap gap-2" aria-label="Selected tickers">
            {selected.length === 0 ? (
              <p className="text-xs text-slate-500">
                No tickers selected yet. Search and pick at least one eligible
                universe equity.
              </p>
            ) : (
              selected.map((ticker) => (
                <span
                  key={ticker}
                  className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-800"
                >
                  {ticker}
                  <button
                    type="button"
                    onClick={() => remove(ticker)}
                    aria-label={`Remove ${ticker}`}
                    className="text-emerald-700 hover:text-emerald-900"
                  >
                    ×
                  </button>
                </span>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default AssetPicker;
