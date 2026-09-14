import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  isTerminalEventStatus,
  useBuildAIPortfolio,
  useBuildStatus,
} from '../../api/aiPortfolio';
import { portfolioKeys } from '../../api/portfolios';
import { paperTradingKeys } from '../../api/paperTrading';
import type { AIEventStatus } from '../../types/api';

/** Risk-profile options accepted by the build endpoint. */
const RISK_PROFILES = ['conservative', 'balanced', 'aggressive'] as const;

/** Presentation per terminal event status. */
const TERMINAL_META: Record<
  Exclude<AIEventStatus, 'queued' | 'running'>,
  { label: string; className: string }
> = {
  succeeded: {
    label: 'Build succeeded',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  },
  partial: {
    label: 'Build partially succeeded',
    className: 'border-amber-200 bg-amber-50 text-amber-800',
  },
  skipped: {
    label: 'Build skipped (market closed)',
    className: 'border-slate-200 bg-slate-50 text-slate-700',
  },
  failed: {
    label: 'Build failed',
    className: 'border-red-300 bg-red-50 text-red-800',
  },
};

/** Parse a comma/space/newline-separated ticker list into normalized symbols. */
function parseTickers(raw: string): string[] {
  return Array.from(
    new Set(
      raw
        .split(/[\s,]+/)
        .map((t) => t.trim().toUpperCase())
        .filter((t) => t.length > 0),
    ),
  );
}

export function BuildAIPortfolioCard() {
  const queryClient = useQueryClient();
  const build = useBuildAIPortfolio();

  const [tickersRaw, setTickersRaw] = useState('');
  const [capital, setCapital] = useState('100000');
  const [riskProfile, setRiskProfile] = useState<string>('balanced');
  const [maxStockCount, setMaxStockCount] = useState('8');
  const [allowNewPicks, setAllowNewPicks] = useState(false);
  const [allowShort, setAllowShort] = useState(false);
  const [dailyRebalancing, setDailyRebalancing] = useState(false);
  const [eventId, setEventId] = useState<string | null>(null);

  const statusQuery = useBuildStatus(eventId);
  const event = statusQuery.data;
  const status = event?.status;
  const terminal = status ? isTerminalEventStatus(status) : false;

  const tickers = parseTickers(tickersRaw);
  const capitalValue = Number.parseFloat(capital);
  const maxStockValue = Number.parseInt(maxStockCount, 10);
  const capitalValid = Number.isFinite(capitalValue) && capitalValue >= 1000;
  const maxStockValid =
    Number.isFinite(maxStockValue) && maxStockValue >= 2 && maxStockValue <= 10;
  const canSubmit = tickers.length >= 2 && capitalValid && maxStockValid;

  // Refresh portfolios + sessions once the build reaches a terminal state.
  const settledEventId = useRef<string | null>(null);
  useEffect(() => {
    if (eventId !== null && terminal && settledEventId.current !== eventId) {
      settledEventId.current = eventId;
      queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
      queryClient.invalidateQueries({ queryKey: paperTradingKeys.all });
    }
  }, [eventId, terminal, queryClient]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    build.mutate(
      {
        tickers,
        allocated_capital: capitalValue,
        risk_profile: riskProfile,
        allow_new_picks: allowNewPicks,
        allow_short: allowShort,
        max_stock_count: maxStockValue,
        daily_rebalancing: dailyRebalancing,
      },
      { onSuccess: (res) => setEventId(res.event_id) },
    );
  };

  const reset = () => {
    setEventId(null);
    build.reset();
  };

  const running = eventId !== null && !terminal;

  return (
    <div className="flex h-full flex-col rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">
        Build an AI portfolio
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Hand a set of candidate tickers to the AI manager. It picks and sizes
        positions, opens a paper-trading session, and can enroll it in daily
        rebalancing.
      </p>

      {/* --------------------------------------------------------------- IDLE */}
      {eventId === null && (
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
          <div>
            <label
              htmlFor="ai-tickers"
              className="block text-sm font-medium text-slate-700"
            >
              Candidate tickers
            </label>
            <textarea
              id="ai-tickers"
              value={tickersRaw}
              onChange={(e) => setTickersRaw(e.target.value)}
              placeholder="e.g. AAPL, MSFT, NVDA, GOOGL"
              rows={2}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
            <p className="mt-1 text-xs text-slate-500">
              At least two, comma- or space-separated.{' '}
              {tickers.length > 0 && (
                <span className="font-medium text-slate-600">
                  {tickers.length} recognized.
                </span>
              )}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label
                htmlFor="ai-capital"
                className="block text-sm font-medium text-slate-700"
              >
                Capital (€)
              </label>
              <input
                id="ai-capital"
                type="number"
                min={1000}
                step={1000}
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            <div>
              <label
                htmlFor="ai-risk"
                className="block text-sm font-medium text-slate-700"
              >
                Risk profile
              </label>
              <select
                id="ai-risk"
                value={riskProfile}
                onChange={(e) => setRiskProfile(e.target.value)}
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {RISK_PROFILES.map((rp) => (
                  <option key={rp} value={rp}>
                    {rp.charAt(0).toUpperCase() + rp.slice(1)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="ai-max-stocks"
                className="block text-sm font-medium text-slate-700"
              >
                Max positions
              </label>
              <input
                id="ai-max-stocks"
                type="number"
                min={2}
                max={10}
                step={1}
                value={maxStockCount}
                onChange={(e) => setMaxStockCount(e.target.value)}
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={allowNewPicks}
                onChange={(e) => setAllowNewPicks(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              Allow the AI to add picks beyond the candidates
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={allowShort}
                onChange={(e) => setAllowShort(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              Allow short positions
            </label>
            <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
              <input
                type="checkbox"
                checked={dailyRebalancing}
                onChange={(e) => setDailyRebalancing(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              Enroll in daily rebalancing
            </label>
          </div>

          {build.isError && (
            <p
              role="alert"
              className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
            >
              Could not start the build. Check your inputs and try again.
            </p>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!canSubmit || build.isPending}
              aria-busy={build.isPending}
              className="rounded bg-emerald-500 px-4 py-2 font-medium text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {build.isPending ? 'Starting…' : 'Build portfolio'}
            </button>
          </div>
        </form>
      )}

      {/* ------------------------------------------------------------ RUNNING */}
      {running && (
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="mt-4 flex flex-col gap-3"
        >
          <span className="flex items-center gap-2 text-sm font-medium text-slate-600">
            <span
              aria-hidden="true"
              className="h-3.5 w-3.5 rounded-full border-2 border-slate-300 border-t-emerald-500 motion-safe:animate-spin"
            />
            Building portfolio…
          </span>
          <span className="inline-flex w-fit items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
            status: {status ?? 'queued'}
          </span>
          <p className="text-xs text-slate-500">
            The AI is selecting and sizing positions. This updates automatically.
          </p>
        </div>
      )}

      {/* ----------------------------------------------------------- TERMINAL */}
      {eventId !== null && terminal && event && status && status !== 'queued' && status !== 'running' && (
        <div className="mt-4 flex flex-col gap-4">
          <div
            role="alert"
            className={`rounded border px-3 py-2 text-sm ${TERMINAL_META[status].className}`}
          >
            <p className="font-semibold">{TERMINAL_META[status].label}</p>
            {event.error && (
              <p className="mt-1 whitespace-pre-wrap break-words">
                {event.error}
              </p>
            )}
            {event.actions_taken && event.actions_taken.length > 0 && (
              <p className="mt-1">
                {event.actions_taken.length} order
                {event.actions_taken.length === 1 ? '' : 's'} placed.
              </p>
            )}
            {dailyRebalancing && status === 'succeeded' && (
              <p className="mt-1">Enrolled in daily rebalancing.</p>
            )}
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={reset}
              className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
            >
              Build another
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default BuildAIPortfolioCard;
