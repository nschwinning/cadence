import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  isTerminalEventStatus,
  useBuildAIPortfolio,
  useBuildStatus,
} from '../../api/aiPortfolio';
import { portfolioKeys } from '../../api/portfolios';
import {
  invalidateSessionDependents,
  useBenchmarks,
} from '../../api/paperTrading';
import type { AIEventStatus } from '../../types/api';

/** Default benchmark id preselected in the build form (S&P 500). */
const DEFAULT_BENCHMARK = 'SP500';

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

/** Human-readable labels for the in-flight event status badge. */
const STATUS_LABELS: Record<string, string> = {
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Succeeded',
  partial: 'Partial',
  skipped: 'Skipped',
  failed: 'Failed',
};

function humanizeStatus(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

/**
 * A labelled number input with an inline unit adornment ($ prefix or % suffix)
 * and a hint line that doubles as its inline validation message (red when the
 * field is invalid). The unit stays in the visible label too so it is part of
 * the accessible name.
 */
function NumberField({
  id,
  label,
  unit,
  unitSide = 'suffix',
  value,
  onChange,
  min,
  max,
  step,
  hint,
  invalid = false,
}: {
  id: string;
  label: string;
  unit?: string;
  unitSide?: 'prefix' | 'suffix';
  value: string;
  onChange: (value: string) => void;
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
  invalid?: boolean;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  const borderClass = invalid
    ? 'border-red-400 focus:border-red-500 focus:ring-red-500'
    : 'border-slate-300 focus:border-emerald-500 focus:ring-emerald-500';
  const padClass =
    unit === undefined
      ? 'px-3'
      : unitSide === 'prefix'
        ? 'pl-7 pr-3'
        : 'pl-3 pr-8';
  return (
    <div>
      <label
        htmlFor={id}
        className="block text-sm font-medium text-slate-700"
      >
        {label}
      </label>
      <div className="relative mt-1">
        {unit !== undefined && unitSide === 'prefix' && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-sm text-slate-400"
          >
            {unit}
          </span>
        )}
        <input
          id={id}
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={invalid || undefined}
          aria-describedby={hintId}
          className={`w-full rounded border py-2 text-sm text-slate-900 focus:outline-none focus:ring-1 ${padClass} ${borderClass}`}
        />
        {unit !== undefined && unitSide === 'suffix' && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3 text-sm text-slate-400"
          >
            {unit}
          </span>
        )}
      </div>
      {hint && (
        <p
          id={hintId}
          className={`mt-1 text-xs ${invalid ? 'text-red-700' : 'text-slate-500'}`}
        >
          {hint}
        </p>
      )}
    </div>
  );
}

export function BuildAIPortfolioCard() {
  const queryClient = useQueryClient();
  const build = useBuildAIPortfolio();

  const [capital, setCapital] = useState('10000');
  const [riskProfile, setRiskProfile] = useState<string>('balanced');
  const [assetTypes, setAssetTypes] = useState<AssetScope>('both');
  const [dailyRebalancing, setDailyRebalancing] = useState(false);
  const [useTechnicalIndicators, setUseTechnicalIndicators] = useState(false);
  const [stopLossEnabled, setStopLossEnabled] = useState(false);
  const [stopLossPct, setStopLossPct] = useState('15');
  const [guardrailsEnabled, setGuardrailsEnabled] = useState(false);
  const [maxAssetPct, setMaxAssetPct] = useState('25');
  const [maxAssetClassPct, setMaxAssetClassPct] = useState('60');
  const [minPositions, setMinPositions] = useState('5');
  const [maxInvestedPct, setMaxInvestedPct] = useState('95');
  const [learningFeedbackEnabled, setLearningFeedbackEnabled] = useState(false);
  const [learningWindow, setLearningWindow] = useState('5');
  const [benchmark, setBenchmark] = useState<string>(DEFAULT_BENCHMARK);
  const [eventId, setEventId] = useState<string | null>(null);

  const { data: benchmarks } = useBenchmarks();
  const benchmarkCatalog = Array.isArray(benchmarks) ? benchmarks : null;

  const statusQuery = useBuildStatus(eventId);
  const event = statusQuery.data;
  const status = event?.status;
  const terminal = status ? isTerminalEventStatus(status) : false;

  const capitalValue = Number.parseFloat(capital);
  const capitalValid = Number.isFinite(capitalValue) && capitalValue >= 1000;

  // The threshold is entered as a percentage (e.g. 15 → 0.15). When the
  // stop-loss is enabled it must be a fraction strictly between 0 and 1.
  const stopLossPctValue = Number.parseFloat(stopLossPct);
  const stopLossFraction = stopLossPctValue / 100;
  const stopLossValid =
    !stopLossEnabled ||
    (Number.isFinite(stopLossPctValue) &&
      stopLossFraction > 0 &&
      stopLossFraction < 1);

  // Guardrail parameters are entered as percentages (max per asset / class /
  // invested) plus an integer minimum position count. When enabled each
  // percentage must be a fraction in (0, 1] and the minimum must be >= 1.
  const maxAssetFraction = Number.parseFloat(maxAssetPct) / 100;
  const maxAssetClassFraction = Number.parseFloat(maxAssetClassPct) / 100;
  const maxInvestedFraction = Number.parseFloat(maxInvestedPct) / 100;
  const minPositionsValue = Number.parseInt(minPositions, 10);
  const fractionInRange = (f: number) => Number.isFinite(f) && f > 0 && f <= 1;
  const minPositionsValid =
    Number.isInteger(minPositionsValue) && minPositionsValue >= 1;
  const guardrailsValid =
    !guardrailsEnabled ||
    (fractionInRange(maxAssetFraction) &&
      fractionInRange(maxAssetClassFraction) &&
      fractionInRange(maxInvestedFraction) &&
      minPositionsValid);

  // The learning window is an integer count of recent days; it must be >= 1
  // when learning feedback is enabled.
  const learningWindowValue = Number.parseInt(learningWindow, 10);
  const learningWindowValid =
    !learningFeedbackEnabled ||
    (Number.isInteger(learningWindowValue) && learningWindowValue >= 1);

  const canSubmit =
    capitalValid && stopLossValid && guardrailsValid && learningWindowValid;

  // Per-field invalid flags drive the inline red hints (only surfaced once the
  // relevant toggle is on so untouched, hidden fields never look erroneous).
  const capitalInvalid = !capitalValid;
  const stopLossInvalid = stopLossEnabled && !stopLossValid;
  const maxAssetInvalid = guardrailsEnabled && !fractionInRange(maxAssetFraction);
  const maxAssetClassInvalid =
    guardrailsEnabled && !fractionInRange(maxAssetClassFraction);
  const maxInvestedInvalid =
    guardrailsEnabled && !fractionInRange(maxInvestedFraction);
  const minPositionsInvalid = guardrailsEnabled && !minPositionsValid;
  const learningWindowInvalid = learningFeedbackEnabled && !learningWindowValid;

  // Refresh portfolios + sessions once the build reaches a terminal state.
  const settledEventId = useRef<string | null>(null);
  useEffect(() => {
    if (eventId !== null && terminal && settledEventId.current !== eventId) {
      settledEventId.current = eventId;
      queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
      // A new session shows up in the sessions list, the runs history and the
      // dashboard tiles/leaderboard — refresh every session-dependent view.
      invalidateSessionDependents(queryClient);
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
        benchmark,
        use_technical_indicators: useTechnicalIndicators,
        stop_loss_enabled: stopLossEnabled,
        stop_loss_pct: stopLossEnabled ? stopLossFraction : null,
        risk_guardrails_enabled: guardrailsEnabled,
        max_allocation_pct: guardrailsEnabled ? maxAssetFraction : null,
        max_asset_class_pct: guardrailsEnabled ? maxAssetClassFraction : null,
        min_positions: guardrailsEnabled ? minPositionsValue : null,
        max_invested_pct: guardrailsEnabled ? maxInvestedFraction : null,
        learning_feedback_enabled: learningFeedbackEnabled,
        learning_feedback_window: learningFeedbackEnabled
          ? learningWindowValue
          : null,
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

          {/* Essentials */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <NumberField
              id="ai-capital"
              label="Capital ($)"
              unit="$"
              unitSide="prefix"
              min={1000}
              step={1000}
              value={capital}
              onChange={setCapital}
              hint="Minimum $1,000."
              invalid={capitalInvalid}
            />
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
            <div>
              <label
                htmlFor="ai-benchmark"
                className="block text-sm font-medium text-slate-700"
              >
                Benchmark
              </label>
              <select
                id="ai-benchmark"
                value={benchmark}
                onChange={(e) => setBenchmark(e.target.value)}
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {(benchmarkCatalog ?? [{ id: DEFAULT_BENCHMARK, name: 'S&P 500' }]).map(
                  (b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ),
                )}
              </select>
            </div>
          </div>

          {/* Daily rebalancing — the primary operating mode. */}
          <div className="flex flex-col gap-1">
            <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
              <input
                type="checkbox"
                checked={dailyRebalancing}
                onChange={(e) => setDailyRebalancing(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              Enroll in daily rebalancing
            </label>
            <p className="text-xs text-slate-500">
              When enabled, the AI re-weights the portfolio toward fresh targets
              every trading day. You can still rebalance manually at any time.
            </p>
          </div>

          {/* Advanced / risk controls — all frozen at build for the session. */}
          <fieldset className="flex flex-col gap-4 border-t border-slate-200 pt-4">
            <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Advanced / risk controls
            </legend>
            <p className="-mt-1 text-xs text-slate-500">
              These settings are frozen for the session&apos;s lifetime.
            </p>

            {/* Technical-indicator strategy. */}
            <div className="flex flex-col gap-1">
              <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
                <input
                  type="checkbox"
                  checked={useTechnicalIndicators}
                  onChange={(e) => setUseTechnicalIndicators(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                />
                Use technical-indicator trend strategy
              </label>
              <p className="text-xs text-slate-500">
                When enabled, the build and every rebalance only enter assets in
                a confirmed uptrend and attach trend context to holdings.
              </p>
            </div>

            {/* Hard stop-loss. */}
            <div className="flex flex-col gap-1">
              <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
                <input
                  type="checkbox"
                  checked={stopLossEnabled}
                  onChange={(e) => setStopLossEnabled(e.target.checked)}
                  aria-expanded={stopLossEnabled}
                  aria-controls="ai-stop-loss-panel"
                  className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                />
                Enable hard stop-loss
              </label>
              <p className="text-xs text-slate-500">
                When enabled, each open position is sold in whole once its market
                price falls to or below its average cost minus this percentage.
              </p>
              {stopLossEnabled && (
                <div
                  id="ai-stop-loss-panel"
                  className="ml-6 mt-1 border-l-2 border-slate-100 pl-4"
                >
                  <div className="sm:w-48">
                    <NumberField
                      id="ai-stop-loss-pct"
                      label="Stop-loss threshold (%)"
                      unit="%"
                      min={1}
                      max={99}
                      step={1}
                      value={stopLossPct}
                      onChange={setStopLossPct}
                      hint="Between 1% and 99% below average cost."
                      invalid={stopLossInvalid}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Deterministic risk guardrails. */}
            <div className="flex flex-col gap-1">
              <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
                <input
                  type="checkbox"
                  checked={guardrailsEnabled}
                  onChange={(e) => setGuardrailsEnabled(e.target.checked)}
                  aria-expanded={guardrailsEnabled}
                  aria-controls="ai-guardrails-panel"
                  className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                />
                Enable risk guardrails
              </label>
              <p className="text-xs text-slate-500">
                When enabled, the target weights are deterministically clamped so
                no single asset or asset class exceeds its cap and the invested
                share stays within the ceiling (the rest held as cash). The
                minimum-positions target is given to the AI as guidance.
              </p>
              {guardrailsEnabled && (
                <div
                  id="ai-guardrails-panel"
                  className="ml-6 mt-1 border-l-2 border-slate-100 pl-4"
                >
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <NumberField
                      id="ai-max-asset-pct"
                      label="Max per asset (%)"
                      unit="%"
                      min={1}
                      max={100}
                      step={1}
                      value={maxAssetPct}
                      onChange={setMaxAssetPct}
                      hint="Cap on any single position (one ticker)."
                      invalid={maxAssetInvalid}
                    />
                    <NumberField
                      id="ai-max-asset-class-pct"
                      label="Max per asset class (%)"
                      unit="%"
                      min={1}
                      max={100}
                      step={1}
                      value={maxAssetClassPct}
                      onChange={setMaxAssetClassPct}
                      hint="Cap on the stocks or crypto bucket."
                      invalid={maxAssetClassInvalid}
                    />
                    <NumberField
                      id="ai-min-positions"
                      label="Min positions"
                      min={1}
                      max={50}
                      step={1}
                      value={minPositions}
                      onChange={setMinPositions}
                      hint="Target number of holdings (count)."
                      invalid={minPositionsInvalid}
                    />
                    <NumberField
                      id="ai-max-invested-pct"
                      label="Max invested (%)"
                      unit="%"
                      min={1}
                      max={100}
                      step={1}
                      value={maxInvestedPct}
                      onChange={setMaxInvestedPct}
                      hint="Remainder is held as cash."
                      invalid={maxInvestedInvalid}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Learning feedback (prior-run outcomes into the rebalance prompt). */}
            <div className="flex flex-col gap-1">
              <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
                <input
                  type="checkbox"
                  checked={learningFeedbackEnabled}
                  onChange={(e) => setLearningFeedbackEnabled(e.target.checked)}
                  aria-expanded={learningFeedbackEnabled}
                  aria-controls="ai-learning-feedback-panel"
                  className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                />
                Enable learning feedback
              </label>
              <p className="text-xs text-slate-500">
                When enabled, each rebalance is shown a compact, cost-forward
                summary of this session's own recent daily outcomes so the AI can
                learn from what its prior decisions produced. Advisory only — it
                adds no hard constraints.
              </p>
              {learningFeedbackEnabled && (
                <div
                  id="ai-learning-feedback-panel"
                  className="ml-6 mt-1 border-l-2 border-slate-100 pl-4"
                >
                  <div className="sm:w-48">
                    <NumberField
                      id="ai-learning-window"
                      label="Learning window (days)"
                      min={1}
                      max={60}
                      step={1}
                      value={learningWindow}
                      onChange={setLearningWindow}
                      hint="Number of recent daily runs to summarize."
                      invalid={learningWindowInvalid}
                    />
                  </div>
                </div>
              )}
            </div>
          </fieldset>

          {build.isError && (
            <p
              role="alert"
              className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
            >
              Could not start the build. Check your inputs and try again.
            </p>
          )}

          <div className="flex flex-wrap items-center justify-end gap-3">
            {!canSubmit && (
              <p className="text-xs text-red-700">
                Fix the highlighted fields before building.
              </p>
            )}
            <button
              type="submit"
              disabled={!canSubmit || build.isPending}
              aria-busy={build.isPending}
              className="rounded bg-emerald-500 px-4 py-2 font-medium text-white hover:bg-emerald-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50"
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
            Status: {humanizeStatus(status ?? 'queued')}
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
