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

/** Asset-scope options (value sent as `asset_types`) with their display labels. */
const ASSET_SCOPES = [
  { value: 'both', label: 'Both' },
  { value: 'stocks', label: 'Stocks only' },
  { value: 'crypto', label: 'Crypto only' },
] as const;

type AssetScope = (typeof ASSET_SCOPES)[number]['value'];

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

export function BuildAIPortfolioCard() {
  const queryClient = useQueryClient();
  const build = useBuildAIPortfolio();

  const [capital, setCapital] = useState('10000');
  const [riskProfile, setRiskProfile] = useState<string>('balanced');
  const [assetTypes, setAssetTypes] = useState<AssetScope>('both');
  const [dailyRebalancing, setDailyRebalancing] = useState(false);
  const [eventId, setEventId] = useState<string | null>(null);

  const statusQuery = useBuildStatus(eventId);
  const event = statusQuery.data;
  const status = event?.status;
  const terminal = status ? isTerminalEventStatus(status) : false;

  const capitalValue = Number.parseFloat(capital);
  const capitalValid = Number.isFinite(capitalValue) && capitalValue >= 1000;
  const canSubmit = capitalValid;

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
        allocated_capital: capitalValue,
        risk_profile: riskProfile,
        asset_types: assetTypes,
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
        The AI manager builds a portfolio across the entire asset universe,
        opens a paper-trading session, and can enroll it in daily rebalancing.
      </p>

      {/* --------------------------------------------------------------- IDLE */}
      {eventId === null && (
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
          <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
            No need to pick tickers — the AI allocates across the app&apos;s
            entire asset universe automatically, deciding each asset&apos;s
            weight and researching new assets as it sees fit.
          </p>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="ai-capital"
                className="block text-sm font-medium text-slate-700"
              >
                Capital ($)
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
                htmlFor="ai-asset-types"
                className="block text-sm font-medium text-slate-700"
              >
                Asset types
              </label>
              <select
                id="ai-asset-types"
                value={assetTypes}
                onChange={(e) => setAssetTypes(e.target.value as AssetScope)}
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {ASSET_SCOPES.map((scope) => (
                  <option key={scope.value} value={scope.value}>
                    {scope.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-2">
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
