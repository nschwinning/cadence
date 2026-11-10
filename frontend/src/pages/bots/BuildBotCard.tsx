import { useEffect, useState } from 'react';
import {
  usePresets,
  useStrategies,
  useCreateBotSession,
} from '../../api/bots';
import { useBenchmarks } from '../../api/paperTrading';
import { AssetPicker } from '../../components/AssetPicker';
import type { BotPreset, BotSessionCreateRequest } from '../../types/api';

/** Default benchmark id preselected in the build form (S&P 500). */
const DEFAULT_BENCHMARK = 'SP500';

/** Strategy selected when the build form first opens. */
const DEFAULT_STRATEGY_KEY = 'ma_crossover';

/** The two Donchian versions shown in the nested Version selector. */
type DonchianVersion = 'turtle' | 'locked';

/** Rolling-Average Reversion axes (mirror the backend params literals). */
type ReversionAverage = 'sma' | 'typical' | 'vwap';
type ReversionDistance = 'band' | 'zscore';
type ReversionExitMode = 'revert' | 'bracket';

/** Risk-control form values a preset sets (percent strings, as the user types them). */
export interface PresetRiskFormValues {
  takeProfitEnabled: boolean;
  /** Percent string, or `null` to keep the field's current value (control off). */
  takeProfitPct: string | null;
  stopLossEnabled: boolean;
  stopLossPct: string | null;
  drawdownStopPct: string;
}

/** Render a fraction (0.005) as the form's percent string ("0.5"). */
function fractionToPercent(fraction: number): string {
  return String(Number((fraction * 100).toFixed(6)));
}

/**
 * Map a preset's risk controls onto the form's percent-based fields. A `null`
 * take-profit / stop-loss turns that control off and leaves its threshold field
 * untouched (so re-enabling it restores the last typed value).
 */
export function presetRiskFormValues(preset: BotPreset): PresetRiskFormValues {
  return {
    takeProfitEnabled: preset.take_profit_pct !== null,
    takeProfitPct:
      preset.take_profit_pct !== null
        ? fractionToPercent(preset.take_profit_pct)
        : null,
    stopLossEnabled: preset.stop_loss_pct !== null,
    stopLossPct:
      preset.stop_loss_pct !== null ? fractionToPercent(preset.stop_loss_pct) : null,
    drawdownStopPct: fractionToPercent(preset.drawdown_stop_pct),
  };
}

/** Numeric tolerance for comparing form values to preset values. */
const PRESET_TOLERANCE = 1e-9;

function sameValue(a: unknown, b: unknown): boolean {
  if (typeof a === 'number' && typeof b === 'number') {
    return Math.abs(a - b) < PRESET_TOLERANCE;
  }
  return a === b;
}

function sameRisk(a: number | null, b: number | null): boolean {
  if (a === null || b === null) return a === b;
  return Math.abs(a - b) < PRESET_TOLERANCE;
}

/**
 * Whether the form's current strategy params and risk controls differ from the
 * applied preset. Derived from values (not a sticky dirty flag), so reverting an
 * edit clears it. The backend's comparison remains authoritative on create.
 */
export function isCustomizedFromPreset(
  preset: BotPreset,
  current: {
    strategyKey: string;
    strategyParams: Record<string, unknown>;
    takeProfitPct: number | null;
    stopLossPct: number | null;
    drawdownStopPct: number;
  },
): boolean {
  if (current.strategyKey !== preset.strategy_key) return true;
  const keys = new Set([
    ...Object.keys(preset.strategy_params),
    ...Object.keys(current.strategyParams),
  ]);
  for (const key of keys) {
    if (!sameValue(preset.strategy_params[key], current.strategyParams[key])) {
      return true;
    }
  }
  return !(
    sameRisk(preset.take_profit_pct, current.takeProfitPct) &&
    sameRisk(preset.stop_loss_pct, current.stopLossPct) &&
    sameRisk(preset.drawdown_stop_pct, current.drawdownStopPct)
  );
}

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
  const presetsQuery = usePresets();
  const presetCatalog = Array.isArray(presetsQuery.data) ? presetsQuery.data : null;

  const [strategyKey, setStrategyKey] = useState(DEFAULT_STRATEGY_KEY);
  const [tickers, setTickers] = useState<string[]>([]);
  const [wholeUniverse, setWholeUniverse] = useState(false);
  const [capital, setCapital] = useState('10000');
  const [benchmark, setBenchmark] = useState<string>(DEFAULT_BENCHMARK);
  const [label, setLabel] = useState('');
  // Strategy parameters and risk controls are filled from the bot preset catalog
  // (course recipes): the selected strategy's default preset on open and on strategy
  // change, the version's preset on a Donchian version change. Every value stays
  // editable; `appliedPresetKey` is sent so the backend records the provenance.
  const [appliedPresetKey, setAppliedPresetKey] = useState<string | null>(null);
  // MA Crossover parameters.
  const [fastPeriod, setFastPeriod] = useState('');
  const [slowPeriod, setSlowPeriod] = useState('');
  // RSI Mean Reversion parameters.
  const [rsiPeriod, setRsiPeriod] = useState('');
  const [oversold, setOversold] = useState('');
  const [exitLevel, setExitLevel] = useState('');
  // Donchian Range Breakout: a nested version plus per-version params. Turtle uses
  // entry / exit channel periods; Locked uses a channel period and an ATR padding
  // multiplier (0 = raw channel).
  const [donchianVersion, setDonchianVersion] = useState<DonchianVersion>('turtle');
  const [entryPeriod, setEntryPeriod] = useState('');
  const [exitPeriod, setExitPeriod] = useState('');
  const [channelPeriod, setChannelPeriod] = useState('');
  const [atrPadding, setAtrPadding] = useState('');
  // Rolling-Average Reversion: average type, window, distance measure (band
  // thresholds entered as percents, z thresholds in standard deviations), exit mode.
  const [raAverage, setRaAverage] = useState<ReversionAverage>('sma');
  const [raWindow, setRaWindow] = useState('');
  const [raDistance, setRaDistance] = useState<ReversionDistance>('band');
  const [raEntryPct, setRaEntryPct] = useState('');
  const [raExitPct, setRaExitPct] = useState('');
  const [raEntryZ, setRaEntryZ] = useState('');
  const [raExitZ, setRaExitZ] = useState('');
  const [raExitMode, setRaExitMode] = useState<ReversionExitMode>('revert');
  // Sizing controls (ATR risk-based by default; all-in is the legacy N=1 method).
  const [sizingMethod, setSizingMethod] = useState('atr_risk');
  const [riskPct, setRiskPct] = useState('1');
  const [atrPeriod, setAtrPeriod] = useState('14');
  const [atrK, setAtrK] = useState('2');
  const [maxPositionPct, setMaxPositionPct] = useState('25');
  const [maxPositions, setMaxPositions] = useState('10');
  // Take-profit / stop-loss come from the preset (off when the preset has none);
  // the user can toggle or retune them. Entered as percents, sent as fractions.
  const [takeProfitEnabled, setTakeProfitEnabled] = useState(false);
  const [takeProfitPct, setTakeProfitPct] = useState('1');
  const [stopLossEnabled, setStopLossEnabled] = useState(false);
  const [stopLossPct, setStopLossPct] = useState('2');
  // The drawdown kill-switch is always on; preloaded from the preset.
  const [drawdownStopPct, setDrawdownStopPct] = useState('');

  // Preset param names → the form field each one fills.
  const paramSetters: Record<string, (value: string) => void> = {
    fast_period: setFastPeriod,
    slow_period: setSlowPeriod,
    period: setRsiPeriod,
    oversold: setOversold,
    exit_level: setExitLevel,
    entry_period: setEntryPeriod,
    exit_period: setExitPeriod,
    channel_period: setChannelPeriod,
    atr_padding_mult: setAtrPadding,
    average_type: (v) => setRaAverage(v as ReversionAverage),
    window: setRaWindow,
    distance: (v) => setRaDistance(v as ReversionDistance),
    // Band thresholds are fractions in the preset but percents in the form.
    entry_threshold: (v) => setRaEntryPct(fractionToPercent(Number(v))),
    exit_threshold: (v) => setRaExitPct(fractionToPercent(Number(v))),
    entry_z: setRaEntryZ,
    exit_z: setRaExitZ,
    exit_mode: (v) => setRaExitMode(v as ReversionExitMode),
  };

  // Fill the strategy params and risk controls from a preset.
  const applyPreset = (preset: BotPreset) => {
    for (const [name, value] of Object.entries(preset.strategy_params)) {
      if (name === 'version') {
        setDonchianVersion(value as DonchianVersion);
      } else {
        paramSetters[name]?.(String(value));
      }
    }
    const risk = presetRiskFormValues(preset);
    setTakeProfitEnabled(risk.takeProfitEnabled);
    if (risk.takeProfitPct !== null) setTakeProfitPct(risk.takeProfitPct);
    setStopLossEnabled(risk.stopLossEnabled);
    if (risk.stopLossPct !== null) setStopLossPct(risk.stopLossPct);
    setDrawdownStopPct(risk.drawdownStopPct);
    setAppliedPresetKey(preset.key);
  };

  const defaultPresetFor = (key: string) =>
    presetCatalog?.find((p) => p.strategy_key === key && p.is_default);

  // Open preconfigured: once the catalog loads, apply the initial strategy's default.
  useEffect(() => {
    if (presetCatalog === null || appliedPresetKey !== null) return;
    const preset = defaultPresetFor(strategyKey);
    if (preset) applyPreset(preset);
    // Runs when the catalog arrives; later changes go through the handlers below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetCatalog]);

  // Switching strategy applies that strategy's default preset.
  const handleStrategyChange = (key: string) => {
    setStrategyKey(key);
    const preset = defaultPresetFor(key);
    if (preset) applyPreset(preset);
  };

  // Switching Donchian version applies the preset for that version.
  const handleVersionChange = (version: DonchianVersion) => {
    setDonchianVersion(version);
    const preset = presetCatalog?.find(
      (p) =>
        p.strategy_key === 'donchian_breakout' &&
        p.strategy_params.version === version,
    );
    if (preset) applyPreset(preset);
  };

  const appliedPreset =
    presetCatalog?.find((p) => p.key === appliedPresetKey) ?? null;
  // The selected strategy's presets; a selector is offered when there are several.
  const strategyPresets =
    presetCatalog?.filter((p) => p.strategy_key === strategyKey) ?? [];
  const showPresetSelector = strategyPresets.length > 1;

  const capitalValue = Number.parseFloat(capital);
  const capitalValid = Number.isFinite(capitalValue) && capitalValue >= 1000;

  // Either an explicit symbol set or the whole-universe flag must be chosen.
  const symbolsValid = wholeUniverse || tickers.length > 0;

  const isMaCrossover = strategyKey === 'ma_crossover';
  const isRsi = strategyKey === 'rsi_mean_reversion';
  const isDonchian = strategyKey === 'donchian_breakout';
  const isDonchianTurtle = isDonchian && donchianVersion === 'turtle';
  const isDonchianLocked = isDonchian && donchianVersion === 'locked';
  const isReversion = strategyKey === 'rolling_average_reversion';
  const isReversionBand = isReversion && raDistance === 'band';
  const isReversionZ = isReversion && raDistance === 'zscore';

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

  // Donchian params. Turtle: integer entry ≥ 2 and exit ≥ 1, exit strictly below
  // entry. Locked: integer channel ≥ 2 and a non-negative ATR padding multiplier.
  const entryPeriodValue = Number.parseInt(entryPeriod, 10);
  const entryPeriodValid = Number.isInteger(entryPeriodValue) && entryPeriodValue >= 2;
  const exitPeriodValue = Number.parseInt(exitPeriod, 10);
  const exitPeriodValid = Number.isInteger(exitPeriodValue) && exitPeriodValue >= 1;
  const donchianPeriodsOrdered =
    entryPeriodValid && exitPeriodValid && exitPeriodValue < entryPeriodValue;
  const channelPeriodValue = Number.parseInt(channelPeriod, 10);
  const channelPeriodValid =
    Number.isInteger(channelPeriodValue) && channelPeriodValue >= 2;
  const atrPaddingValue = Number.parseFloat(atrPadding);
  const atrPaddingValid = Number.isFinite(atrPaddingValue) && atrPaddingValue >= 0;
  const donchianParamsValid =
    !isDonchian ||
    (donchianVersion === 'turtle'
      ? entryPeriodValid && exitPeriodValid && donchianPeriodsOrdered
      : channelPeriodValid && atrPaddingValid);

  // Rolling-Average Reversion params: integer window ≥ 2; band thresholds as percents
  // in [0, 100); z thresholds ≥ 0. In revert mode the exit level must sit strictly
  // above the entry level (exit < entry), otherwise an entry could exit at once.
  const raWindowValue = Number.parseInt(raWindow, 10);
  const raWindowValid = Number.isInteger(raWindowValue) && raWindowValue >= 2;
  const raEntryFraction = Number.parseFloat(raEntryPct) / 100;
  const raExitFraction = Number.parseFloat(raExitPct) / 100;
  const raEntryPctValid =
    Number.isFinite(raEntryFraction) && raEntryFraction >= 0 && raEntryFraction < 1;
  const raExitPctValid =
    Number.isFinite(raExitFraction) && raExitFraction >= 0 && raExitFraction < 1;
  const raEntryZValue = Number.parseFloat(raEntryZ);
  const raExitZValue = Number.parseFloat(raExitZ);
  const raEntryZValid = Number.isFinite(raEntryZValue) && raEntryZValue >= 0;
  const raExitZValid = Number.isFinite(raExitZValue) && raExitZValue >= 0;
  const raReverting = raExitMode === 'revert';
  const raBandOrdered =
    !raReverting ||
    (raEntryPctValid && raExitPctValid && raExitFraction < raEntryFraction);
  const raZOrdered =
    !raReverting || (raEntryZValid && raExitZValid && raExitZValue < raEntryZValue);
  const reversionParamsValid =
    !isReversion ||
    (raWindowValid &&
      raEntryPctValid &&
      raExitPctValid &&
      raEntryZValid &&
      raExitZValid &&
      (raDistance === 'band' ? raBandOrdered : raZOrdered));

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

  // Build the strategy-specific params payload for the selected strategy (and, for
  // Donchian, the selected version).
  const donchianParams: Record<string, unknown> =
    donchianVersion === 'turtle'
      ? {
          version: 'turtle',
          entry_period: entryPeriodValue,
          exit_period: exitPeriodValue,
        }
      : {
          version: 'locked',
          channel_period: channelPeriodValue,
          atr_padding_mult: atrPaddingValue,
        };
  // Rolling-Average Reversion always sends all eight fields (off-mode ones included),
  // matching the preset's full params dict so the customized check stays exact.
  const reversionParams: Record<string, unknown> = {
    average_type: raAverage,
    window: raWindowValue,
    distance: raDistance,
    entry_threshold: raEntryFraction,
    exit_threshold: raExitFraction,
    entry_z: raEntryZValue,
    exit_z: raExitZValue,
    exit_mode: raExitMode,
  };
  const strategyParams: Record<string, unknown> = isRsi
    ? {
        period: rsiPeriodValue,
        oversold: oversoldValue,
        exit_level: exitLevelValue,
      }
    : isDonchian
      ? donchianParams
      : isReversion
        ? reversionParams
        : { fast_period: fastValue, slow_period: slowValue };

  const customized =
    appliedPreset !== null &&
    isCustomizedFromPreset(appliedPreset, {
      strategyKey,
      strategyParams,
      takeProfitPct: takeProfitEnabled ? takeProfitFraction : null,
      stopLossPct: stopLossEnabled ? stopLossFraction : null,
      drawdownStopPct: drawdownFraction,
    });

  const canSubmit =
    appliedPreset !== null &&
    strategyKey.length > 0 &&
    symbolsValid &&
    capitalValid &&
    maParamsValid &&
    rsiParamsValid &&
    donchianParamsValid &&
    reversionParamsValid &&
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
  const entryPeriodInvalid =
    isDonchianTurtle &&
    entryPeriod.length > 0 &&
    (!entryPeriodValid || !donchianPeriodsOrdered);
  const exitPeriodInvalid =
    isDonchianTurtle &&
    exitPeriod.length > 0 &&
    (!exitPeriodValid || !donchianPeriodsOrdered);
  const channelPeriodInvalid =
    isDonchianLocked && channelPeriod.length > 0 && !channelPeriodValid;
  const atrPaddingInvalid =
    isDonchianLocked && atrPadding.length > 0 && !atrPaddingValid;
  const raWindowInvalid = isReversion && raWindow.length > 0 && !raWindowValid;
  const raEntryPctInvalid =
    isReversionBand && raEntryPct.length > 0 && (!raEntryPctValid || !raBandOrdered);
  const raExitPctInvalid =
    isReversionBand && raExitPct.length > 0 && (!raExitPctValid || !raBandOrdered);
  const raEntryZInvalid =
    isReversionZ && raEntryZ.length > 0 && (!raEntryZValid || !raZOrdered);
  const raExitZInvalid =
    isReversionZ && raExitZ.length > 0 && (!raExitZValid || !raZOrdered);
  const riskInvalid = isAtr && riskPct.length > 0 && !riskValid;
  const atrPeriodInvalid = isAtr && atrPeriod.length > 0 && !atrPeriodValid;
  const atrKInvalid = isAtr && atrK.length > 0 && !atrKValid;
  const maxPositionInvalid = isAtr && maxPositionPct.length > 0 && !maxPositionValid;
  const maxPositionsInvalid = maxPositions.length > 0 && !maxPositionsValid;
  const takeProfitInvalid = takeProfitEnabled && !takeProfitValid;
  const stopLossInvalid = stopLossEnabled && !stopLossValid;
  const drawdownInvalid = drawdownStopPct.length > 0 && !drawdownValid;


  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    const request: BotSessionCreateRequest = {
      strategy_key: strategyKey,
      preset_key: appliedPresetKey,
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
              {presetsQuery.isError ? (
                <p role="alert" className="mt-1 text-xs text-red-700">
                  Could not load the strategy presets. Reload to try again.
                </p>
              ) : appliedPreset ? (
                <p
                  className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500"
                  data-testid="bot-preset-indicator"
                >
                  {!showPresetSelector && (
                    <span>
                      Preset:{' '}
                      <span className="font-medium text-slate-700">
                        {appliedPreset.display_name}
                      </span>
                    </span>
                  )}
                  {customized && (
                    <>
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 font-medium text-amber-800">
                        Customized
                      </span>
                      <button
                        type="button"
                        onClick={() => applyPreset(appliedPreset)}
                        className="text-emerald-700 underline hover:text-emerald-800"
                      >
                        Reset to preset
                      </button>
                    </>
                  )}
                </p>
              ) : (
                <p className="mt-1 text-xs text-slate-500">Loading presets…</p>
              )}
            </div>
            {showPresetSelector && (
              <div>
                <label
                  htmlFor="bot-preset"
                  className="block text-sm font-medium text-slate-700"
                >
                  Preset
                </label>
                <select
                  id="bot-preset"
                  value={appliedPresetKey ?? ''}
                  onChange={(e) => {
                    const preset = strategyPresets.find(
                      (p) => p.key === e.target.value,
                    );
                    if (preset) applyPreset(preset);
                  }}
                  className={FIELD_CLASS}
                >
                  {strategyPresets.map((p) => (
                    <option key={p.key} value={p.key}>
                      {p.display_name}
                    </option>
                  ))}
                </select>
                {appliedPreset && (
                  <p className="mt-1 text-xs text-slate-500">
                    {appliedPreset.description}
                  </p>
                )}
              </div>
            )}
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
            ) : isDonchian ? (
              <div className="flex flex-col gap-3">
                <div>
                  <label
                    htmlFor="bot-donchian-version"
                    className="block text-sm font-medium text-slate-700"
                  >
                    Version
                  </label>
                  <select
                    id="bot-donchian-version"
                    value={donchianVersion}
                    onChange={(e) =>
                      handleVersionChange(e.target.value as DonchianVersion)
                    }
                    className={FIELD_CLASS}
                  >
                    <option value="turtle">Turtle rolling channel</option>
                    <option value="locked">Locked channel</option>
                  </select>
                  <p className="mt-1 text-xs text-slate-500">
                    {donchianVersion === 'turtle'
                      ? 'Enters above the entry-channel high and exits below the exit-channel low.'
                      : 'Enters above the (optionally ATR-padded) channel high; the exit is left to the risk controls below.'}
                  </p>
                </div>
                {donchianVersion === 'turtle' ? (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <NumberField
                      id="bot-entry-period"
                      label="Entry channel period"
                      min={2}
                      step={1}
                      value={entryPeriod}
                      onChange={setEntryPeriod}
                      hint="Bars in the breakout (entry) high. Must be above the exit period."
                      invalid={entryPeriodInvalid}
                    />
                    <NumberField
                      id="bot-exit-period"
                      label="Exit channel period"
                      min={1}
                      step={1}
                      value={exitPeriod}
                      onChange={setExitPeriod}
                      hint="Bars in the breakdown (exit) low. Must be below the entry period."
                      invalid={exitPeriodInvalid}
                    />
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <NumberField
                      id="bot-channel-period"
                      label="Channel period"
                      min={2}
                      step={1}
                      value={channelPeriod}
                      onChange={setChannelPeriod}
                      hint="Bars in the breakout channel high."
                      invalid={channelPeriodInvalid}
                    />
                    <NumberField
                      id="bot-atr-padding"
                      label="ATR padding (×)"
                      min={0}
                      step={0.1}
                      value={atrPadding}
                      onChange={setAtrPadding}
                      hint="Pads the channel outward by this × ATR. 0 = raw channel."
                      invalid={atrPaddingInvalid}
                    />
                  </div>
                )}
              </div>
            ) : isReversion ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="bot-ra-average"
                    className="block text-sm font-medium text-slate-700"
                  >
                    Average
                  </label>
                  <select
                    id="bot-ra-average"
                    value={raAverage}
                    onChange={(e) => setRaAverage(e.target.value as ReversionAverage)}
                    className={FIELD_CLASS}
                  >
                    <option value="sma">Simple average of closes</option>
                    <option value="typical">Typical price (H+L+C)/3</option>
                    <option value="vwap">Volume-weighted (VWAP)</option>
                  </select>
                </div>
                <NumberField
                  id="bot-ra-window"
                  label="Window (bars)"
                  min={2}
                  step={1}
                  value={raWindow}
                  onChange={setRaWindow}
                  hint="Bars in the rolling average, including the latest."
                  invalid={raWindowInvalid}
                />
                <div>
                  <label
                    htmlFor="bot-ra-distance"
                    className="block text-sm font-medium text-slate-700"
                  >
                    Distance
                  </label>
                  <select
                    id="bot-ra-distance"
                    value={raDistance}
                    onChange={(e) =>
                      setRaDistance(e.target.value as ReversionDistance)
                    }
                    className={FIELD_CLASS}
                  >
                    <option value="band">Percentage band</option>
                    <option value="zscore">Z-score (std devs)</option>
                  </select>
                </div>
                <div>
                  <label
                    htmlFor="bot-ra-exit-mode"
                    className="block text-sm font-medium text-slate-700"
                  >
                    Exit
                  </label>
                  <select
                    id="bot-ra-exit-mode"
                    value={raExitMode}
                    onChange={(e) =>
                      setRaExitMode(e.target.value as ReversionExitMode)
                    }
                    className={FIELD_CLASS}
                  >
                    <option value="revert">Revert to the average</option>
                    <option value="bracket">Hold, exit via take-profit / stop-loss</option>
                  </select>
                </div>
                {raDistance === 'band' ? (
                  <>
                    <NumberField
                      id="bot-ra-entry-pct"
                      label="Entry below average (%)"
                      min={0}
                      step={0.1}
                      value={raEntryPct}
                      onChange={setRaEntryPct}
                      hint="Buy when the close is this far below. 0 = any close below."
                      invalid={raEntryPctInvalid}
                    />
                    <NumberField
                      id="bot-ra-exit-pct"
                      label="Exit within average (%)"
                      min={0}
                      step={0.1}
                      value={raExitPct}
                      onChange={setRaExitPct}
                      hint={
                        raExitMode === 'revert'
                          ? 'Sell once back within this of the average. Must be below the entry.'
                          : 'Unused while exits go via take-profit / stop-loss.'
                      }
                      invalid={raExitPctInvalid}
                    />
                  </>
                ) : (
                  <>
                    <NumberField
                      id="bot-ra-entry-z"
                      label="Entry z-score (σ below)"
                      min={0}
                      step={0.1}
                      value={raEntryZ}
                      onChange={setRaEntryZ}
                      hint="Buy when the close is this many std devs below."
                      invalid={raEntryZInvalid}
                    />
                    <NumberField
                      id="bot-ra-exit-z"
                      label="Exit z-score (σ below)"
                      min={0}
                      step={0.1}
                      value={raExitZ}
                      onChange={setRaExitZ}
                      hint={
                        raExitMode === 'revert'
                          ? 'Sell once back above this many std devs below. Must be below the entry.'
                          : 'Unused while exits go via take-profit / stop-loss.'
                      }
                      invalid={raExitZInvalid}
                    />
                  </>
                )}
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
                hint="Liquidates all positions and stops the bot when total value falls this far from its peak. Always on; preloaded from the strategy's preset."
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
