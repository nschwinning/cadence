import { useState } from 'react';
import { useStrategies, useCreateBotSession } from '../../api/bots';
import { useBenchmarks } from '../../api/paperTrading';
import { AssetPicker } from '../../components/AssetPicker';
import type { BotSessionCreateRequest } from '../../types/api';

/** Default benchmark id preselected in the build form (S&P 500). */
const DEFAULT_BENCHMARK = 'SP500';

/** Strategy selected when the build form first opens. */
const DEFAULT_STRATEGY_KEY = 'ma_crossover';

/**
 * Course-recipe defaults for the shared engine risk controls, keyed by strategy.
 * The form opens pre-tuned to the selected strategy's reference algo, and these
 * values are re-applied whenever the strategy dropdown changes (the strategy's
 * own parameters live in their own state, seeded to course values below):
 *   `ma_crossover` → course Algo 6 (fast 5 / slow 12, TP 1% / SL 2% / drawdown 5%).
 *   `rsi_mean_reversion` → course Algo 16 (period 14 / oversold 30 / exit 50,
 *     TP 0.5% / SL 1% / drawdown 5%).
 * The user can still change any of them before building.
 */
const STRATEGY_RISK_DEFAULTS: Record<
  string,
  {
    takeProfitEnabled: boolean;
    takeProfitPct: string;
    stopLossEnabled: boolean;
    stopLossPct: string;
    drawdownStopPct: string;
  }
> = {
  ma_crossover: {
    takeProfitEnabled: true,
    takeProfitPct: '1',
    stopLossEnabled: true,
    stopLossPct: '2',
    drawdownStopPct: '5',
  },
  rsi_mean_reversion: {
    takeProfitEnabled: true,
    takeProfitPct: '0.5',
    stopLossEnabled: true,
    stopLossPct: '1',
    drawdownStopPct: '5',
  },
};

const DEFAULT_RISK = STRATEGY_RISK_DEFAULTS[DEFAULT_STRATEGY_KEY];

/** Shared classes for the plain `<select>` / `<input>` controls. */
const FIELD_CLASS =
  'mt-1 w-full rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500';

/** Shared classes for a single optional-control card. */
const CONTROL_CARD_CLASS =
  'flex flex-col gap-1 rounded-lg border border-slate-200 p-3';

/**
 * A labelled number input with a hint line that doubles as its inline validation
 * message (red when the field is invalid).
 */
function NumberField({
  id,
  label,
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
        aria-describedby={hintId}
        className={`mt-1 w-full rounded border px-3 py-1.5 text-sm text-slate-900 focus:outline-none focus:ring-1 ${borderClass}`}
      />
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

/**
 * Build form for a deterministic strategy bot. One bot trades a *set* of eligible
 * universe equities from a single shared, hard-capped capital pool (the initial
 * capital is the budget; open-position cost can never exceed it). The user picks the
 * symbol set (or the whole universe) with the universe-backed picker, the strategy's
 * parameters (MA Crossover's fast / slow SMA periods in v1), and ATR risk-based
 * sizing controls (per-name cap, max concurrent positions), plus optional take-profit,
 * stop-loss, drawdown kill-switch, and cash-buffer controls. On success it navigates
 * to the new bot's detail page.
 */
export function BuildBotCard() {
  const create = useCreateBotSession();
  const { data: strategies } = useStrategies();
  const strategyCatalog = Array.isArray(strategies) ? strategies : null;
  const { data: benchmarks } = useBenchmarks();
  const benchmarkCatalog = Array.isArray(benchmarks) ? benchmarks : null;

  const [strategyKey, setStrategyKey] = useState(DEFAULT_STRATEGY_KEY);
  const [tickers, setTickers] = useState<string[]>([]);
  const [wholeUniverse, setWholeUniverse] = useState(false);
  const [capital, setCapital] = useState('10000');
  const [benchmark, setBenchmark] = useState<string>(DEFAULT_BENCHMARK);
  const [label, setLabel] = useState('');
  // MA Crossover parameters (course Algo 6 defaults 5 / 12).
  const [fastPeriod, setFastPeriod] = useState('5');
  const [slowPeriod, setSlowPeriod] = useState('12');
  // RSI Mean Reversion parameters (course defaults 14 / 30 / 50).
  const [rsiPeriod, setRsiPeriod] = useState('14');
  const [oversold, setOversold] = useState('30');
  const [exitLevel, setExitLevel] = useState('50');
  // Sizing controls (ATR risk-based by default; all-in is the legacy N=1 method).
  const [sizingMethod, setSizingMethod] = useState('atr_risk');
  const [riskPct, setRiskPct] = useState('1');
  const [atrPeriod, setAtrPeriod] = useState('14');
  const [atrK, setAtrK] = useState('2');
  const [maxPositionPct, setMaxPositionPct] = useState('25');
  const [maxPositions, setMaxPositions] = useState('10');
  // Take-profit / stop-loss preloaded with the strategy's course recipe (on by
  // default); the user can disable or retune them.
  const [takeProfitEnabled, setTakeProfitEnabled] = useState(
    DEFAULT_RISK.takeProfitEnabled,
  );
  const [takeProfitPct, setTakeProfitPct] = useState(DEFAULT_RISK.takeProfitPct);
  const [stopLossEnabled, setStopLossEnabled] = useState(
    DEFAULT_RISK.stopLossEnabled,
  );
  const [stopLossPct, setStopLossPct] = useState(DEFAULT_RISK.stopLossPct);
  // The drawdown kill-switch is always on. The field is preloaded with the
  // strategy's course default (5%); the user can change it. Entered as a percent,
  // sent as a fraction.
  const [drawdownStopPct, setDrawdownStopPct] = useState(
    DEFAULT_RISK.drawdownStopPct,
  );

  // Switching strategy re-applies that strategy's course risk recipe (TP / SL /
  // drawdown differ per reference algo). The strategy-specific parameter fields
  // keep their own course-seeded state.
  const handleStrategyChange = (key: string) => {
    setStrategyKey(key);
    const risk = STRATEGY_RISK_DEFAULTS[key];
    if (!risk) return;
    setTakeProfitEnabled(risk.takeProfitEnabled);
    setTakeProfitPct(risk.takeProfitPct);
    setStopLossEnabled(risk.stopLossEnabled);
    setStopLossPct(risk.stopLossPct);
    setDrawdownStopPct(risk.drawdownStopPct);
  };

  const capitalValue = Number.parseFloat(capital);
  const capitalValid = Number.isFinite(capitalValue) && capitalValue >= 1000;

  // Either an explicit symbol set or the whole-universe flag must be chosen.
  const symbolsValid = wholeUniverse || tickers.length > 0;

  const isMaCrossover = strategyKey === 'ma_crossover';
  const isRsi = strategyKey === 'rsi_mean_reversion';

  const fastValue = Number.parseInt(fastPeriod, 10);
  const slowValue = Number.parseInt(slowPeriod, 10);
  const fastValid = Number.isInteger(fastValue) && fastValue >= 1;
  const slowValid = Number.isInteger(slowValue) && slowValue >= 2;
  // The MA Crossover strategy requires the fast period strictly below the slow one.
  const periodsOrdered = fastValid && slowValid && fastValue < slowValue;
  // Only the MA Crossover strategy's params gate submit when it is selected.
  const maParamsValid = !isMaCrossover || (fastValid && slowValid && periodsOrdered);

  // RSI Mean Reversion params: integer period ≥ 1, thresholds in 0–100, and the
  // oversold level strictly below the exit level (otherwise the bands overlap).
  const rsiPeriodValue = Number.parseInt(rsiPeriod, 10);
  const rsiPeriodValid = Number.isInteger(rsiPeriodValue) && rsiPeriodValue >= 1;
  const oversoldValue = Number.parseFloat(oversold);
  const oversoldValid =
    Number.isFinite(oversoldValue) && oversoldValue >= 0 && oversoldValue <= 100;
  const exitLevelValue = Number.parseFloat(exitLevel);
  const exitLevelValid =
    Number.isFinite(exitLevelValue) && exitLevelValue >= 0 && exitLevelValue <= 100;
  const bandsOrdered =
    oversoldValid && exitLevelValid && oversoldValue < exitLevelValue;
  const rsiParamsValid =
    !isRsi || (rsiPeriodValid && oversoldValid && exitLevelValid && bandsOrdered);

  const isAtr = sizingMethod === 'atr_risk';
  // ATR sizing params are entered in friendly units: risk/cap as percentages.
  const riskFraction = Number.parseFloat(riskPct) / 100;
  const riskValid =
    !isAtr || (Number.isFinite(riskFraction) && riskFraction > 0 && riskFraction < 1);
  const atrPeriodValue = Number.parseInt(atrPeriod, 10);
  const atrPeriodValid = !isAtr || (Number.isInteger(atrPeriodValue) && atrPeriodValue >= 1);
  const atrKValue = Number.parseFloat(atrK);
  const atrKValid = !isAtr || (Number.isFinite(atrKValue) && atrKValue > 0);
  const maxPositionFraction = Number.parseFloat(maxPositionPct) / 100;
  const maxPositionValid =
    !isAtr ||
    (Number.isFinite(maxPositionFraction) &&
      maxPositionFraction > 0 &&
      maxPositionFraction <= 1);
  const maxPositionsValue = Number.parseInt(maxPositions, 10);
  const maxPositionsValid =
    Number.isInteger(maxPositionsValue) && maxPositionsValue >= 1;

  // TP / SL are entered as percentages (e.g. 20 → 0.20); each must be > 0 when on.
  const takeProfitFraction = Number.parseFloat(takeProfitPct) / 100;
  const takeProfitValid =
    !takeProfitEnabled ||
    (Number.isFinite(takeProfitFraction) && takeProfitFraction > 0);
  const stopLossFraction = Number.parseFloat(stopLossPct) / 100;
  const stopLossValid =
    !stopLossEnabled ||
    (Number.isFinite(stopLossFraction) && stopLossFraction > 0);

  // Drawdown kill-switch: always on, entered as a percent (e.g. 5 → 0.05); must be a
  // fraction strictly between 0 and 1.
  const drawdownFraction = Number.parseFloat(drawdownStopPct) / 100;
  const drawdownValid =
    Number.isFinite(drawdownFraction) &&
    drawdownFraction > 0 &&
    drawdownFraction < 1;

  const canSubmit =
    strategyKey.length > 0 &&
    symbolsValid &&
    capitalValid &&
    maParamsValid &&
    rsiParamsValid &&
    riskValid &&
    atrPeriodValid &&
    atrKValid &&
    maxPositionValid &&
    maxPositionsValid &&
    takeProfitValid &&
    stopLossValid &&
    drawdownValid;

  const capitalInvalid = !capitalValid;
  const fastInvalid = fastPeriod.length > 0 && (!fastValid || !periodsOrdered);
  const slowInvalid = slowPeriod.length > 0 && (!slowValid || !periodsOrdered);
  const rsiPeriodInvalid = rsiPeriod.length > 0 && !rsiPeriodValid;
  const oversoldInvalid =
    oversold.length > 0 && (!oversoldValid || !bandsOrdered);
  const exitLevelInvalid =
    exitLevel.length > 0 && (!exitLevelValid || !bandsOrdered);
  const riskInvalid = isAtr && riskPct.length > 0 && !riskValid;
  const atrPeriodInvalid = isAtr && atrPeriod.length > 0 && !atrPeriodValid;
  const atrKInvalid = isAtr && atrK.length > 0 && !atrKValid;
  const maxPositionInvalid = isAtr && maxPositionPct.length > 0 && !maxPositionValid;
  const maxPositionsInvalid = maxPositions.length > 0 && !maxPositionsValid;
  const takeProfitInvalid = takeProfitEnabled && !takeProfitValid;
  const stopLossInvalid = stopLossEnabled && !stopLossValid;
  const drawdownInvalid = drawdownStopPct.length > 0 && !drawdownValid;

  // Build the strategy-specific params payload for the selected strategy.
  const strategyParams = isRsi
    ? {
        period: rsiPeriodValue,
        oversold: oversoldValue,
        exit_level: exitLevelValue,
      }
    : { fast_period: fastValue, slow_period: slowValue };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    const request: BotSessionCreateRequest = {
      strategy_key: strategyKey,
      tickers: wholeUniverse ? null : tickers,
      whole_universe: wholeUniverse,
      initial_capital: capitalValue,
      benchmark,
      strategy_params: strategyParams,
      label: label.trim() === '' ? null : label.trim(),
      sizing_method: sizingMethod,
      risk_pct: isAtr ? riskFraction : null,
      atr_period: isAtr ? atrPeriodValue : null,
      atr_k: isAtr ? atrKValue : null,
      max_position_pct: isAtr ? maxPositionFraction : null,
      max_positions: maxPositionsValue,
      take_profit_pct: takeProfitEnabled ? takeProfitFraction : null,
      stop_loss_pct: stopLossEnabled ? stopLossFraction : null,
      drawdown_stop_pct: drawdownFraction,
    };
    create.mutate(request);
  };

  return (
    <div className="flex flex-col rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-base font-semibold text-slate-900">Build a bot</h2>
      <p className="mt-1 text-xs text-slate-500">
        Creates a deterministic, rule-based bot that trades a set of equities from
        the asset universe on an intraday cron tick — no AI. All positions share one
        capped capital pool: the bot can never commit more than its initial capital,
        no matter how many names signal.
      </p>

      <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-5">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
          {/* LEFT — bot basics */}
          <div className="flex flex-col gap-4 lg:col-span-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Bot basics
            </h3>
            <div>
              <label
                htmlFor="bot-strategy"
                className="block text-sm font-medium text-slate-700"
              >
                Strategy
              </label>
              <select
                id="bot-strategy"
                value={strategyKey}
                onChange={(e) => handleStrategyChange(e.target.value)}
                className={FIELD_CLASS}
              >
                {(
                  strategyCatalog ?? [
                    {
                      key: 'ma_crossover',
                      display_name: 'MA Crossover',
                      explanation: '',
                      required_history: 51,
                      params_schema: {},
                    },
                  ]
                ).map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.display_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <span className="block text-sm font-medium text-slate-700">
                Tickers
              </span>
              <p className="mt-0.5 text-xs text-slate-500">
                Pick one or more eligible universe equities, or trade the whole
                universe.
              </p>
              <div className="mt-2">
                <AssetPicker
                  selected={tickers}
                  onChange={setTickers}
                  wholeUniverse={wholeUniverse}
                  onWholeUniverseChange={setWholeUniverse}
                />
              </div>
            </div>
            <NumberField
              id="bot-capital"
              label="Initial capital ($)"
              min={1000}
              step={1000}
              value={capital}
              onChange={setCapital}
              hint="The shared budget. Minimum $1,000."
              invalid={capitalInvalid}
            />
            <div>
              <label
                htmlFor="bot-benchmark"
                className="block text-sm font-medium text-slate-700"
              >
                Benchmark
              </label>
              <select
                id="bot-benchmark"
                value={benchmark}
                onChange={(e) => setBenchmark(e.target.value)}
                className={FIELD_CLASS}
              >
                {(
                  benchmarkCatalog ?? [{ id: DEFAULT_BENCHMARK, name: 'S&P 500' }]
                ).map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="bot-label"
                className="block text-sm font-medium text-slate-700"
              >
                Label (optional)
              </label>
              <input
                id="bot-label"
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Defaults to strategy + tickers"
                className={FIELD_CLASS}
              />
            </div>
          </div>

          {/* RIGHT — strategy params, sizing, optional risk controls */}
          <div className="flex flex-col gap-4 border-t border-slate-200 pt-4 lg:col-span-3 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Strategy parameters
            </h3>
            {isRsi ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <NumberField
                  id="bot-rsi-period"
                  label="RSI period"
                  min={1}
                  step={1}
                  value={rsiPeriod}
                  onChange={setRsiPeriod}
                  hint="Bars in the RSI window."
                  invalid={rsiPeriodInvalid}
                />
                <NumberField
                  id="bot-oversold"
                  label="Oversold level"
                  min={0}
                  max={100}
                  step={1}
                  value={oversold}
                  onChange={setOversold}
                  hint="Buy below this RSI. Must be under the exit level."
                  invalid={oversoldInvalid}
                />
                <NumberField
                  id="bot-exit-level"
                  label="Exit level"
                  min={0}
                  max={100}
                  step={1}
                  value={exitLevel}
                  onChange={setExitLevel}
                  hint="Exit above this RSI. Must be over the oversold level."
                  invalid={exitLevelInvalid}
                />
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <NumberField
                  id="bot-fast-period"
                  label="Fast SMA period"
                  min={1}
                  step={1}
                  value={fastPeriod}
                  onChange={setFastPeriod}
                  hint="Must be below the slow period."
                  invalid={fastInvalid}
                />
                <NumberField
                  id="bot-slow-period"
                  label="Slow SMA period"
                  min={2}
                  step={1}
                  value={slowPeriod}
                  onChange={setSlowPeriod}
                  hint="Must be above the fast period."
                  invalid={slowInvalid}
                />
              </div>
            )}

            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Position sizing
            </h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="bot-sizing-method"
                  className="block text-sm font-medium text-slate-700"
                >
                  Sizing method
                </label>
                <select
                  id="bot-sizing-method"
                  value={sizingMethod}
                  onChange={(e) => setSizingMethod(e.target.value)}
                  className={FIELD_CLASS}
                >
                  <option value="atr_risk">ATR risk-based</option>
                  <option value="all_in">All-in (single name)</option>
                </select>
              </div>
              <NumberField
                id="bot-max-positions"
                label="Max concurrent positions"
                min={1}
                step={1}
                value={maxPositions}
                onChange={setMaxPositions}
                hint="Cap on names held at once."
                invalid={maxPositionsInvalid}
              />
              {isAtr && (
                <>
                  <NumberField
                    id="bot-risk-pct"
                    label="Risk per position (%)"
                    min={0.1}
                    step={0.1}
                    value={riskPct}
                    onChange={setRiskPct}
                    hint="Target dollar risk = budget × this."
                    invalid={riskInvalid}
                  />
                  <NumberField
                    id="bot-max-position-pct"
                    label="Max per-name (% of budget)"
                    min={1}
                    step={1}
                    value={maxPositionPct}
                    onChange={setMaxPositionPct}
                    hint="Caps any one position's size."
                    invalid={maxPositionInvalid}
                  />
                  <NumberField
                    id="bot-atr-period"
                    label="ATR period"
                    min={1}
                    step={1}
                    value={atrPeriod}
                    onChange={setAtrPeriod}
                    hint="Bars of true-range history."
                    invalid={atrPeriodInvalid}
                  />
                  <NumberField
                    id="bot-atr-k"
                    label="ATR multiplier (k)"
                    min={0.1}
                    step={0.1}
                    value={atrK}
                    onChange={setAtrK}
                    hint="Per-share risk = k × ATR."
                    invalid={atrKInvalid}
                  />
                </>
              )}
            </div>

            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Optional risk controls
            </h3>
            <div className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2">
              {/* Take-profit. */}
              <div className={CONTROL_CARD_CLASS}>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
                  <input
                    type="checkbox"
                    checked={takeProfitEnabled}
                    onChange={(e) => setTakeProfitEnabled(e.target.checked)}
                    aria-controls="bot-take-profit-panel"
                    aria-expanded={takeProfitEnabled}
                    className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  Enable take-profit
                </label>
                <p className="text-xs text-slate-500">
                  Exit a position once its price rises this far above the entry
                  price, regardless of the strategy signal.
                </p>
                {takeProfitEnabled && (
                  <div
                    id="bot-take-profit-panel"
                    className="mt-1 border-l-2 border-slate-100 pl-3"
                  >
                    <NumberField
                      id="bot-take-profit-pct"
                      label="Take-profit threshold (%)"
                      min={0.1}
                      step={0.1}
                      value={takeProfitPct}
                      onChange={setTakeProfitPct}
                      hint="Above the entry price."
                      invalid={takeProfitInvalid}
                    />
                  </div>
                )}
              </div>

              {/* Stop-loss. */}
              <div className={CONTROL_CARD_CLASS}>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
                  <input
                    type="checkbox"
                    checked={stopLossEnabled}
                    onChange={(e) => setStopLossEnabled(e.target.checked)}
                    aria-controls="bot-stop-loss-panel"
                    aria-expanded={stopLossEnabled}
                    className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  Enable stop-loss
                </label>
                <p className="text-xs text-slate-500">
                  Exit a position once its price falls this far below the entry
                  price, regardless of the strategy signal.
                </p>
                {stopLossEnabled && (
                  <div
                    id="bot-stop-loss-panel"
                    className="mt-1 border-l-2 border-slate-100 pl-3"
                  >
                    <NumberField
                      id="bot-stop-loss-pct"
                      label="Stop-loss threshold (%)"
                      min={0.1}
                      step={0.1}
                      value={stopLossPct}
                      onChange={setStopLossPct}
                      hint="Below the entry price."
                      invalid={stopLossInvalid}
                    />
                  </div>
                )}
              </div>
            </div>

            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Drawdown kill-switch
            </h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <NumberField
                id="bot-drawdown-pct"
                label="Drawdown kill-switch (%)"
                min={0.1}
                step={0.1}
                value={drawdownStopPct}
                onChange={setDrawdownStopPct}
                hint="Liquidates all positions and stops the bot when total value falls this far from its peak. Always on; preloaded with the strategy's course default."
                invalid={drawdownInvalid}
              />
            </div>
          </div>
        </div>

        {create.isError && (
          <p
            role="alert"
            className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
          >
            Could not create the bot. Check the tickers are eligible equities and
            the parameters are valid, then try again.
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
            disabled={!canSubmit || create.isPending}
            aria-busy={create.isPending}
            className="rounded bg-emerald-500 px-4 py-2 font-medium text-white hover:bg-emerald-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {create.isPending ? 'Creating…' : 'Create bot'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default BuildBotCard;
