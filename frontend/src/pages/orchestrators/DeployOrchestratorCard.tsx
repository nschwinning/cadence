import { useState } from 'react';
import { useCreateOrchestrator } from '../../api/orchestrators';
import { useBenchmarks, useModels } from '../../api/paperTrading';
import type { BotOrchestratorCreateRequest } from '../../types/api';
import { CADENCE_LABELS } from './orchestratorUi';

/** Smallest capital pool an orchestrator may be deployed with (mirrors the backend). */
export const MIN_ORCHESTRATOR_CAPITAL = 5000;

const FIELD_CLASS =
  'mt-1 w-full rounded border px-3 py-1.5 text-sm text-slate-900 focus:outline-none focus:ring-1';
const OK_BORDER = 'border-slate-300 focus:border-emerald-500 focus:ring-emerald-500';
const BAD_BORDER = 'border-red-400 focus:border-red-500 focus:ring-red-500';

function NumberInput({
  id,
  label,
  value,
  onChange,
  hint,
  invalid,
  min,
  max,
  step,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint: string;
  invalid: boolean;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={invalid || undefined}
        aria-describedby={`${id}-hint`}
        className={`${FIELD_CLASS} ${invalid ? BAD_BORDER : OK_BORDER}`}
      />
      <p
        id={`${id}-hint`}
        className={`mt-1 text-xs ${invalid ? 'text-red-700' : 'text-slate-500'}`}
      >
        {hint}
      </p>
    </div>
  );
}

function inRange(value: number, min: number, max: number): boolean {
  return Number.isInteger(value) && value >= min && value <= max;
}

/**
 * Deploy form for a bot orchestrator: a capital pool plus the limits the AI must
 * respect (parallel bots, share per bot, tickers per bot), its decision cadence,
 * AI model and benchmark. Pre-filled with the defaults; navigates to the new
 * orchestrator on success. Deploying creates no bots — the first decision run does.
 */
export function DeployOrchestratorCard() {
  const create = useCreateOrchestrator();
  const { data: models } = useModels();
  const modelCatalog = Array.isArray(models) ? models : [];
  const { data: benchmarks } = useBenchmarks();
  const benchmarkCatalog = Array.isArray(benchmarks)
    ? benchmarks
    : [{ id: 'SP500', name: 'S&P 500' }];

  const [label, setLabel] = useState('');
  const [capital, setCapital] = useState('10000');
  const [maxBots, setMaxBots] = useState('3');
  const [maxSharePct, setMaxSharePct] = useState('50');
  const [maxTickers, setMaxTickers] = useState('5');
  const [cadence, setCadence] = useState('daily');
  const [model, setModel] = useState('');
  const [benchmark, setBenchmark] = useState('SP500');

  const capitalValue = Number.parseFloat(capital);
  const capitalValid =
    Number.isFinite(capitalValue) && capitalValue >= MIN_ORCHESTRATOR_CAPITAL;
  const maxBotsValue = Number.parseInt(maxBots, 10);
  const maxBotsValid = inRange(maxBotsValue, 1, 10);
  const shareFraction = Number.parseFloat(maxSharePct) / 100;
  const shareValid =
    Number.isFinite(shareFraction) && shareFraction > 0 && shareFraction <= 1;
  const maxTickersValue = Number.parseInt(maxTickers, 10);
  const maxTickersValid = inRange(maxTickersValue, 1, 10);
  const labelValid = label.trim().length > 0;

  const canSubmit =
    labelValid && capitalValid && maxBotsValid && shareValid && maxTickersValid;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    const request: BotOrchestratorCreateRequest = {
      label: label.trim(),
      capital: capitalValue,
      max_parallel_bots: maxBotsValue,
      max_bot_share: shareFraction,
      max_tickers_per_bot: maxTickersValue,
      cadence,
      model: model === '' ? null : model,
      benchmark,
    };
    create.mutate(request);
  };

  return (
    <div className="flex flex-col rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-base font-semibold text-slate-900">Deploy an orchestrator</h2>
      <p className="mt-1 text-xs text-slate-500">
        An AI that manages a portfolio of strategy bots from the course presets. Before
        each market open on its cadence it reads market and sector conditions, then
        deploys preset bots on tickers it picks and stops bots whose setup is gone — always
        within the limits below.
      </p>

      <form onSubmit={handleSubmit} className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label
            htmlFor="orchestrator-label"
            className="block text-sm font-medium text-slate-700"
          >
            Name
          </label>
          <input
            id="orchestrator-label"
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Core rotation"
            className={`${FIELD_CLASS} ${OK_BORDER}`}
          />
        </div>
        <NumberInput
          id="orchestrator-capital"
          label="Capital pool ($)"
          min={MIN_ORCHESTRATOR_CAPITAL}
          step={0.01}
          value={capital}
          onChange={setCapital}
          hint="Shared by all its bots; gains and losses flow back in. Minimum $5,000."
          invalid={!capitalValid}
        />
        <NumberInput
          id="orchestrator-max-bots"
          label="Max parallel bots"
          min={1}
          max={10}
          step={1}
          value={maxBots}
          onChange={setMaxBots}
          hint="Bots running at once (1–10)."
          invalid={!maxBotsValid}
        />
        <NumberInput
          id="orchestrator-max-share"
          label="Max per bot (% of pool)"
          min={1}
          max={100}
          step={1}
          value={maxSharePct}
          onChange={setMaxSharePct}
          hint="Caps any one bot's capital. Every bot gets at least $1,000."
          invalid={!shareValid}
        />
        <NumberInput
          id="orchestrator-max-tickers"
          label="Max tickers per bot"
          min={1}
          max={10}
          step={1}
          value={maxTickers}
          onChange={setMaxTickers}
          hint="Tickers the AI may give one bot (1–10)."
          invalid={!maxTickersValid}
        />
        <div>
          <label
            htmlFor="orchestrator-cadence"
            className="block text-sm font-medium text-slate-700"
          >
            Decision cadence
          </label>
          <select
            id="orchestrator-cadence"
            value={cadence}
            onChange={(e) => setCadence(e.target.value)}
            className={`${FIELD_CLASS} ${OK_BORDER}`}
          >
            {Object.entries(CADENCE_LABELS).map(([value, name]) => (
              <option key={value} value={value}>
                {name}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-500">Runs at 09:00 ET, before the open.</p>
        </div>
        <div>
          <label
            htmlFor="orchestrator-model"
            className="block text-sm font-medium text-slate-700"
          >
            AI model
          </label>
          <select
            id="orchestrator-model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className={`${FIELD_CLASS} ${OK_BORDER}`}
          >
            <option value="">Default model</option>
            {modelCatalog.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor="orchestrator-benchmark"
            className="block text-sm font-medium text-slate-700"
          >
            Benchmark
          </label>
          <select
            id="orchestrator-benchmark"
            value={benchmark}
            onChange={(e) => setBenchmark(e.target.value)}
            className={`${FIELD_CLASS} ${OK_BORDER}`}
          >
            {benchmarkCatalog.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </div>

        {create.isError && (
          <p
            role="alert"
            className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 sm:col-span-2"
          >
            Could not deploy the orchestrator. Check the limits and try again.
          </p>
        )}

        <div className="flex flex-wrap items-center justify-end gap-3 sm:col-span-2">
          {!canSubmit && (
            <p className="text-xs text-red-700">
              {labelValid ? 'Fix the highlighted fields.' : 'Give the orchestrator a name.'}
            </p>
          )}
          <button
            type="submit"
            disabled={!canSubmit || create.isPending}
            aria-busy={create.isPending}
            className="rounded bg-emerald-500 px-4 py-2 font-medium text-white hover:bg-emerald-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {create.isPending ? 'Deploying…' : 'Deploy orchestrator'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default DeployOrchestratorCard;
