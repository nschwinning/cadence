import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { assetKeys, SUPPORTED_CATEGORIES } from '../../api/assets';
import {
  isTerminalPhase,
  useCreateRecommendationRun,
  useRecommendationRun,
} from '../../api/recommendations';
import { CATEGORY_STYLES } from '../../components/CategoryBadge';
import type {
  AssetCategory,
  CandidateOutcome,
  RecommendationCandidateResult,
  RunPhase,
} from '../../types/api';

/** The three in-flight phases rendered as stepper nodes (in order). */
const PHASE_STEPS: { phase: RunPhase; label: string; caption: string }[] = [
  { phase: 'queued', label: 'Queued', caption: 'Waiting to start…' },
  {
    phase: 'searching',
    label: 'Searching',
    caption: 'Asking the AI for candidate tickers…',
  },
  {
    phase: 'validating',
    label: 'Validating',
    caption: 'Checking eligibility & duplicates…',
  },
];

/** Presentation per candidate outcome: pill label/colors, dot, and sort order. */
const OUTCOME_META: Record<
  CandidateOutcome,
  { label: string; pill: string; dot: string; order: number }
> = {
  added: {
    label: 'Added',
    pill: 'bg-emerald-100 text-emerald-800',
    dot: 'bg-emerald-500',
    order: 0,
  },
  'skipped-duplicate': {
    label: 'Duplicate',
    pill: 'bg-slate-100 text-slate-700',
    dot: 'bg-slate-400',
    order: 1,
  },
  'skipped-ineligible': {
    label: 'Ineligible',
    pill: 'bg-red-100 text-red-800',
    dot: 'bg-red-500',
    order: 2,
  },
  error: {
    label: 'Error',
    pill: 'bg-amber-100 text-amber-800',
    dot: 'bg-amber-500',
    order: 3,
  },
};

/** Format elapsed seconds as `m:ss`. */
function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

/** A single toggle chip for a category, `role="checkbox"`, reusing badge colors. */
function CategoryChip({
  category,
  selected,
  onToggle,
}: {
  category: AssetCategory;
  selected: boolean;
  onToggle: () => void;
}) {
  const { label, className } = CATEGORY_STYLES[category];
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={selected}
      onClick={onToggle}
      className={
        selected
          ? `inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm font-medium ring-1 ring-emerald-500 ${className} focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1`
          : 'inline-flex items-center gap-1 rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1'
      }
    >
      {selected && <span aria-hidden="true">✓</span>}
      {label}
    </button>
  );
}

/** Node visual state within the horizontal stepper. */
type NodeState = 'done' | 'current' | 'queued-current' | 'upcoming' | 'failed';

function StepNode({ state, index }: { state: NodeState; index: number }) {
  const base =
    'flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold';
  const byState: Record<NodeState, string> = {
    done: 'bg-emerald-500 text-white',
    current:
      'bg-emerald-500 text-white ring-4 ring-emerald-100 motion-safe:animate-pulse',
    'queued-current':
      'bg-slate-400 text-white ring-4 ring-slate-100 motion-safe:animate-pulse',
    upcoming: 'bg-slate-200 text-slate-400',
    failed: 'bg-red-500 text-white',
  };
  let glyph: string;
  if (state === 'done') glyph = '✓';
  else if (state === 'failed') glyph = '✕';
  else glyph = String(index + 1);
  return (
    <span aria-hidden="true" className={`${base} ${byState[state]}`}>
      {glyph}
    </span>
  );
}

/** The horizontal stepper across the run's phases. */
function Stepper({ phase }: { phase: RunPhase }) {
  const terminal = isTerminalPhase(phase);
  const failed = phase === 'failed';
  const completed = phase === 'completed';
  const activeIndex = PHASE_STEPS.findIndex((s) => s.phase === phase);

  const inFlightState = (i: number): NodeState => {
    if (terminal) return 'done';
    if (i < activeIndex) return 'done';
    if (i === activeIndex) {
      return phase === 'queued' ? 'queued-current' : 'current';
    }
    return 'upcoming';
  };

  const finalState: NodeState = completed
    ? 'done'
    : failed
      ? 'failed'
      : 'upcoming';
  const finalLabel = completed ? 'Completed' : failed ? 'Failed' : 'Done';

  const connectorDone = (i: number): boolean => {
    if (terminal) return !failed;
    return i < activeIndex;
  };

  const labelColor = (i: number): string => {
    if (!terminal && i === activeIndex) {
      return phase === 'queued'
        ? 'text-slate-600'
        : 'text-emerald-700 font-medium';
    }
    if (terminal || i < activeIndex) return 'text-emerald-700';
    return 'text-slate-400';
  };

  return (
    <div>
      <div className="flex items-center gap-2">
        {PHASE_STEPS.map((step, i) => (
          <div key={step.phase} className="flex flex-1 items-center gap-2">
            <StepNode state={inFlightState(i)} index={i} />
            <span
              className={`h-0.5 flex-1 rounded ${
                connectorDone(i) ? 'bg-emerald-500' : 'bg-slate-200'
              }`}
            />
          </div>
        ))}
        <StepNode state={finalState} index={PHASE_STEPS.length} />
      </div>
      <div className="mt-2 grid grid-cols-4 text-xs">
        {PHASE_STEPS.map((step, i) => (
          <span key={step.phase} className={labelColor(i)}>
            {step.label}
          </span>
        ))}
        <span
          className={
            completed
              ? 'text-emerald-700'
              : failed
                ? 'text-red-700'
                : 'text-slate-400'
          }
        >
          {finalLabel}
        </span>
      </div>
    </div>
  );
}

/** Derived rollup counts over a run's candidate results. */
function rollup(results: RecommendationCandidateResult[]) {
  let added = 0;
  let duplicate = 0;
  let ineligible = 0;
  let errored = 0;
  for (const r of results) {
    if (r.outcome === 'added') added += 1;
    else if (r.outcome === 'skipped-duplicate') duplicate += 1;
    else if (r.outcome === 'skipped-ineligible') ineligible += 1;
    else errored += 1;
  }
  return {
    added,
    duplicate,
    ineligible,
    errored,
    skipped: duplicate + ineligible,
  };
}

export interface RecommendAssetsCardProps {
  /** Called when the user follows the "appears below" link; scrolls/focuses the table. */
  onViewUniverse?: () => void;
}

export function RecommendAssetsCard({ onViewUniverse }: RecommendAssetsCardProps) {
  const queryClient = useQueryClient();
  const createRun = useCreateRecommendationRun();

  const [count, setCount] = useState('5');
  const [categories, setCategories] = useState<AssetCategory[]>([]);
  const [runId, setRunId] = useState<number | null>(null);

  const runQuery = useRecommendationRun(runId);
  const run = runQuery.data;
  const phase = run?.status;
  const terminal = phase ? isTerminalPhase(phase) : false;

  const countValue = Number.parseInt(count, 10);
  const countValid = Number.isFinite(countValue) && countValue >= 1;
  const canSubmit = countValid && categories.length >= 1;

  // One-shot: invalidate the assets list exactly once when a run completes so the
  // universe table renders newly added assets. Guarded per run id.
  const invalidatedRunId = useRef<number | null>(null);
  useEffect(() => {
    if (
      runId !== null &&
      phase === 'completed' &&
      invalidatedRunId.current !== runId
    ) {
      invalidatedRunId.current = runId;
      queryClient.invalidateQueries({ queryKey: assetKeys.all });
    }
  }, [runId, phase, queryClient]);

  // Move focus to the result heading when the run reaches a terminal state.
  const resultHeadingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (terminal) resultHeadingRef.current?.focus();
  }, [terminal]);

  // Elapsed timer while a run is in progress (a "this is live" cue).
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (runId === null || terminal) return;
    setElapsed(0);
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [runId, terminal]);

  const toggleCategory = (category: AssetCategory) => {
    setCategories((prev) =>
      prev.includes(category)
        ? prev.filter((c) => c !== category)
        : [...prev, category],
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    createRun.mutate(
      { count: countValue, categories },
      { onSuccess: (created) => setRunId(created.id) },
    );
  };

  const handleBlurCount = () => {
    if (!countValid) setCount('1');
  };

  const reset = () => {
    setRunId(null);
    createRun.reset();
  };

  const running = runId !== null && !terminal;

  return (
    <div className="flex h-full flex-col rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Recommend assets</h2>
      <p className="mt-1 text-sm text-slate-500">
        Let Cadence&apos;s AI suggest new assets and auto-add the ones that pass
        eligibility.
      </p>

      {/* ---------------------------------------------------------------- IDLE */}
      {runId === null && (
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
          <div>
            <label
              htmlFor="rec-count"
              className="block text-sm font-medium text-slate-700"
            >
              How many to add (up to)
            </label>
            <div className="mt-1 flex items-center gap-3">
              <input
                id="rec-count"
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                value={count}
                onChange={(e) => setCount(e.target.value)}
                onBlur={handleBlurCount}
                aria-describedby="rec-count-help"
                className="w-28 rounded border border-slate-300 px-3 py-2 text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              <span id="rec-count-help" className="text-xs text-slate-500">
                We&apos;ll add at most this many eligible new assets.
              </span>
            </div>
          </div>

          <div>
            <span
              id="rec-cat-label"
              className="block text-sm font-medium text-slate-700"
            >
              Categories
            </span>
            <div
              role="group"
              aria-labelledby="rec-cat-label"
              className="mt-1 flex flex-wrap gap-2"
            >
              {SUPPORTED_CATEGORIES.map((category) => (
                <CategoryChip
                  key={category}
                  category={category}
                  selected={categories.includes(category)}
                  onToggle={() => toggleCategory(category)}
                />
              ))}
            </div>
            {categories.length === 0 && (
              <p className="mt-1 text-xs text-slate-500">
                Select at least one category.
              </p>
            )}
          </div>

          {createRun.isError && (
            <p
              role="alert"
              className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
            >
              Could not start the recommendation run. Please try again.
            </p>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!canSubmit || createRun.isPending}
              aria-busy={createRun.isPending}
              className="rounded bg-emerald-500 px-4 py-2 font-medium text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {createRun.isPending ? 'Recommend…' : 'Recommend'}
            </button>
          </div>
        </form>
      )}

      {/* ------------------------------------------------------------- RUNNING */}
      {running && (
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="mt-4 flex flex-col gap-3"
        >
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-xs font-medium text-slate-500">
              <span
                aria-hidden="true"
                className="h-3.5 w-3.5 rounded-full border-2 border-slate-300 border-t-emerald-500 motion-safe:animate-spin"
              />
              Live status
            </span>
            <span className="flex items-center gap-3">
              <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
                phase: {phase ?? 'queued'}
              </span>
              <span className="text-xs tabular-nums text-slate-400">
                {formatElapsed(elapsed)}
              </span>
            </span>
          </div>

          <Stepper phase={phase ?? 'queued'} />

          <p className="text-xs text-slate-500">
            {PHASE_STEPS.find((s) => s.phase === (phase ?? 'queued'))?.caption ??
              'Waiting to start…'}
          </p>

          {run && (
            <p className="text-xs text-slate-500">
              Requested up to {run.requested_count} · categories:{' '}
              {run.requested_categories
                .map((c) => CATEGORY_STYLES[c as AssetCategory]?.label ?? c)
                .join(', ')}
            </p>
          )}
        </div>
      )}

      {/* ----------------------------------------------------------- COMPLETED */}
      {runId !== null && phase === 'completed' && run && (
        <CompletedSummary
          results={run.results}
          headingRef={resultHeadingRef}
          onViewUniverse={onViewUniverse}
          onReset={reset}
        />
      )}

      {/* -------------------------------------------------------------- FAILED */}
      {runId !== null && phase === 'failed' && run && (
        <div className="mt-4 flex flex-col gap-4">
          <Stepper phase="failed" />
          <div
            role="alert"
            className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
          >
            <p
              ref={resultHeadingRef}
              tabIndex={-1}
              className="font-semibold focus:outline-none"
            >
              Recommendation run failed.
            </p>
            <p className="mt-1 whitespace-pre-wrap break-words text-sm text-red-800">
              {run.error && run.error.trim().length > 0
                ? run.error
                : 'An unknown error occurred.'}
            </p>
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={reset}
              className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
            >
              Try again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function CompletedSummary({
  results,
  headingRef,
  onViewUniverse,
  onReset,
}: {
  results: RecommendationCandidateResult[];
  headingRef: React.RefObject<HTMLHeadingElement | null>;
  onViewUniverse?: () => void;
  onReset: () => void;
}) {
  const { added, duplicate, ineligible, errored, skipped } = rollup(results);
  const errorWord = errored === 1 ? 'error' : 'errors';
  const assetWord = added === 1 ? 'asset' : 'assets';
  const sorted = [...results].sort(
    (a, b) => OUTCOME_META[a.outcome].order - OUTCOME_META[b.outcome].order,
  );

  return (
    <div className="mt-4 flex flex-col gap-4">
      <Stepper phase="completed" />

      <h3
        ref={headingRef}
        tabIndex={-1}
        className="text-sm font-semibold text-slate-900 focus:outline-none"
      >
        Recommendation complete
      </h3>

      {added > 0 ? (
        <div
          role="alert"
          className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
        >
          Added <strong>{added}</strong> new {assetWord}. Skipped {skipped} (
          {duplicate} duplicate, {ineligible} ineligible), {errored} {errorWord}.
        </div>
      ) : results.length === 0 ? (
        <div
          role="alert"
          className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700"
        >
          The recommender returned no candidates to evaluate — there was nothing
          new to add. This is expected in offline (stub) mode once the stub&apos;s
          fixed pool is already in your universe; configure the live recommender
          to discover new assets.
        </div>
      ) : (
        <div
          role="alert"
          className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700"
        >
          No new assets were added — every candidate was skipped ({duplicate}{' '}
          duplicate, {ineligible} ineligible), {errored} {errorWord}. See details
          below.
        </div>
      )}

      {added > 0 && (
        <p className="text-sm text-slate-600">
          New assets now appear in the{' '}
          <button
            type="button"
            onClick={onViewUniverse}
            className="text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
          >
            Asset universe
          </button>{' '}
          below.
        </p>
      )}

      <ul
        className={`flex flex-col ${
          sorted.length > 8
            ? 'max-h-64 overflow-y-auto rounded border border-slate-100'
            : ''
        }`}
      >
        {sorted.length > 0 &&
          sorted.map((result, i) => {
          const meta = OUTCOME_META[result.outcome];
          return (
            <li
              key={`${result.ticker}-${i}`}
              className="flex items-center gap-2 border-b border-slate-100 py-1.5 text-sm last:border-b-0"
            >
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.pill}`}
              >
                <span
                  aria-hidden="true"
                  className={`h-1.5 w-1.5 rounded-full ${meta.dot}`}
                />
                {meta.label}
              </span>
              <span className="font-semibold tabular-nums text-slate-900">
                {result.ticker}
              </span>
              {result.detail && (
                <span className="text-xs text-slate-500">{result.detail}</span>
              )}
            </li>
          );
        })}
      </ul>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={onReset}
          className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
        >
          Recommend more
        </button>
      </div>
    </div>
  );
}

export default RecommendAssetsCard;
