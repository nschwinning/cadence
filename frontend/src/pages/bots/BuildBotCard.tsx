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
/** ATR-Band Trend versions (mirror the backend params literal). */
type AtrBandVersion = 'supertrend' | 'keltner';

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
  // ATR-Band Trend: version (SuperTrend / Keltner), window, ATR multiplier, and the
  // Keltner-only exit below the midline.
  const [abVersion, setAbVersion] = useState<AtrBandVersion>('supertrend');
  const [abWindow, setAbWindow] = useState('');
  const [abMult, setAbMult] = useState('');
  const [abExitOnMidline, setAbExitOnMidline] = useState(true);
  // ADX Trend Strength: ADX period and threshold.
  const [adxPeriod, setAdxPeriod] = useState('');
  const [adxThreshold, setAdxThreshold] = useState('');
  // MACD Momentum: fast / slow / signal EMA periods.
  const [macdFast, setMacdFast] = useState('');
  const [macdSlow, setMacdSlow] = useState('');
  const [macdSignal, setMacdSignal] = useState('');
  // Trend Confirmation: trend (SMA), momentum (MACD), strength (RSI) legs, plus the
  // optional rate-of-change and on-balance-volume legs.
  const [tcSmaFast, setTcSmaFast] = useState('');
  const [tcSmaSlow, setTcSmaSlow] = useState('');
  const [tcMacdFast, setTcMacdFast] = useState('');
  const [tcMacdSlow, setTcMacdSlow] = useState('');
  const [tcMacdSignal, setTcMacdSignal] = useState('');
  const [tcRsiPeriod, setTcRsiPeriod] = useState('');
  const [tcRsiEntry, setTcRsiEntry] = useState('');
  const [tcRsiMax, setTcRsiMax] = useState('');
  const [tcRsiExit, setTcRsiExit] = useState('');
  const [tcUseRoc, setTcUseRoc] = useState(false);
  const [tcRocPeriod, setTcRocPeriod] = useState('12');
  const [tcUseObv, setTcUseObv] = useState(false);
  const [tcObvWindow, setTcObvWindow] = useState('20');
  // Price Velocity Reversal: the drop threshold, entered in percent per bar.
  const [pvThresholdPct, setPvThresholdPct] = useState('');
  // VAMA: lookback, smoothing range, and fixed (course) vs adaptive smoothing.
  const [vamaLookback, setVamaLookback] = useState('');
  const [vamaAlphaMin, setVamaAlphaMin] = useState('');
  const [vamaAlphaMax, setVamaAlphaMax] = useState('');
  const [vamaAdaptive, setVamaAdaptive] = useState(false);
  // MA Ribbon: fast / mid / slow simple moving average periods.
  const [ribbonFast, setRibbonFast] = useState('');
  const [ribbonMid, setRibbonMid] = useState('');
  const [ribbonSlow, setRibbonSlow] = useState('');
  // HMA Trend: fast / slow Hull Moving Average periods.
  const [hmaFast, setHmaFast] = useState('');
  const [hmaSlow, setHmaSlow] = useState('');
  // Heikin-Ashi Trend: the optional above-average-volume filter (course Algo 37).
  const [haVolumeFilter, setHaVolumeFilter] = useState(false);
  const [haVolumeWindow, setHaVolumeWindow] = useState('20');
  // Rolling-Average Reversion's optional ADX danger exit (course Algo 15).
  const [raAdxExit, setRaAdxExit] = useState(false);
  const [raAdxLookback, setRaAdxLookback] = useState('20');
  const [raAdxThreshold, setRaAdxThreshold] = useState('20');
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
    adx_exit: (v) => setRaAdxExit(v === 'true'),
    adx_lookback: setRaAdxLookback,
    adx_threshold: setRaAdxThreshold,
  };
  // Trend Confirmation's fields (its param names are unique, but booleans need care).
  const trendConfirmationSetters: Record<string, (value: unknown) => void> = {
    sma_fast: (v) => setTcSmaFast(String(v)),
    sma_slow: (v) => setTcSmaSlow(String(v)),
    macd_fast: (v) => setTcMacdFast(String(v)),
    macd_slow: (v) => setTcMacdSlow(String(v)),
    macd_signal: (v) => setTcMacdSignal(String(v)),
    rsi_period: (v) => setTcRsiPeriod(String(v)),
    rsi_entry: (v) => setTcRsiEntry(String(v)),
    rsi_max: (v) => setTcRsiMax(String(v)),
    rsi_exit: (v) => setTcRsiExit(String(v)),
    use_roc: (v) => setTcUseRoc(Boolean(v)),
    roc_period: (v) => setTcRocPeriod(String(v)),
    use_obv: (v) => setTcUseObv(Boolean(v)),
    obv_window: (v) => setTcObvWindow(String(v)),
  };
  // MACD Momentum's `fast_period` / `slow_period` would collide with MA Crossover's.
  const macdSetters: Record<string, (value: string) => void> = {
    fast_period: setMacdFast,
    slow_period: setMacdSlow,
    signal_period: setMacdSignal,
  };
  // ADX Trend Strength's `period` / `threshold` would collide with RSI's `period`.
  const adxSetters: Record<string, (value: string) => void> = {
    period: setAdxPeriod,
    threshold: setAdxThreshold,
  };

  // ATR-Band Trend shares param names (version, window) with other strategies, so its
  // presets fill their own fields.
  const atrBandSetters: Record<string, (value: unknown) => void> = {
    version: (v) => setAbVersion(v as AtrBandVersion),
    window: (v) => setAbWindow(String(v)),
    atr_mult: (v) => setAbMult(String(v)),
    exit_on_midline: (v) => setAbExitOnMidline(Boolean(v)),
  };

  // Fill the strategy params and risk controls from a preset.
  const applyPreset = (preset: BotPreset) => {
    if (preset.strategy_key === 'heikin_ashi_trend') {
      // Presets without the volume filter leave it off at its default window.
      setHaVolumeFilter(false);
      setHaVolumeWindow('20');
    }
    if (preset.strategy_key === 'rolling_average_reversion') {
      // Presets without the ADX danger exit leave it off (and at its defaults).
      setRaAdxExit(false);
      setRaAdxLookback('20');
      setRaAdxThreshold('20');
    }
    for (const [name, value] of Object.entries(preset.strategy_params)) {
      if (preset.strategy_key === 'atr_band_trend') {
        atrBandSetters[name]?.(value);
      } else if (preset.strategy_key === 'adx_trend') {
        adxSetters[name]?.(String(value));
      } else if (preset.strategy_key === 'macd_momentum') {
        macdSetters[name]?.(String(value));
      } else if (preset.strategy_key === 'trend_confirmation') {
        trendConfirmationSetters[name]?.(value);
      } else if (preset.strategy_key === 'price_velocity_reversal') {
        // The threshold is a fraction in the preset but a percent in the form.
        if (name === 'threshold_pct') setPvThresholdPct(fractionToPercent(Number(value)));
      } else if (preset.strategy_key === 'vama') {
        if (name === 'lookback') setVamaLookback(String(value));
        if (name === 'alpha_min') setVamaAlphaMin(String(value));
        if (name === 'alpha_max') setVamaAlphaMax(String(value));
        if (name === 'adaptive') setVamaAdaptive(Boolean(value));
      } else if (preset.strategy_key === 'ma_ribbon') {
        // `fast_period` / `slow_period` would collide with MA Crossover's fields.
        if (name === 'fast_period') setRibbonFast(String(value));
        if (name === 'mid_period') setRibbonMid(String(value));
        if (name === 'slow_period') setRibbonSlow(String(value));
      } else if (preset.strategy_key === 'hma_trend') {
        // `fast_period` / `slow_period` would collide with MA Crossover's fields.
        if (name === 'fast_period') setHmaFast(String(value));
        if (name === 'slow_period') setHmaSlow(String(value));
      } else if (preset.strategy_key === 'heikin_ashi_trend') {
        if (name === 'volume_filter') setHaVolumeFilter(Boolean(value));
        if (name === 'volume_window') setHaVolumeWindow(String(value));
      } else if (name === 'version') {
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

  // Switching ATR-Band version applies the preset for that version.
  const handleAtrBandVersionChange = (version: AtrBandVersion) => {
    setAbVersion(version);
    const preset = presetCatalog?.find(
      (p) =>
        p.strategy_key === 'atr_band_trend' && p.strategy_params.version === version,
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
  const isAtrBand = strategyKey === 'atr_band_trend';
  const isAdx = strategyKey === 'adx_trend';
  const isMacd = strategyKey === 'macd_momentum';
  const isHeikinAshi = strategyKey === 'heikin_ashi_trend';
  const isHma = strategyKey === 'hma_trend';
  const isRibbon = strategyKey === 'ma_ribbon';
  const isVama = strategyKey === 'vama';
  const isVelocity = strategyKey === 'price_velocity_reversal';
  const isTrendConfirmation = strategyKey === 'trend_confirmation';

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
  // in [0, 100); z thresholds ≥ 0. In revert mode the exit level must not sit below the
  // entry level (exit ≤ entry); equal is fine — entry is strict, the exit is at-or-above.
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
    (raEntryPctValid && raExitPctValid && raExitFraction <= raEntryFraction);
  const raZOrdered =
    !raReverting || (raEntryZValid && raExitZValid && raExitZValue <= raEntryZValue);
  const reversionParamsValid =
    !isReversion ||
    (raWindowValid &&
      raEntryPctValid &&
      raExitPctValid &&
      raEntryZValid &&
      raExitZValid &&
      (raDistance === 'band' ? raBandOrdered : raZOrdered));

  // ATR-Band Trend params: integer window ≥ 2 and a positive ATR multiplier.
  const abWindowValue = Number.parseInt(abWindow, 10);
  const abWindowValid = Number.isInteger(abWindowValue) && abWindowValue >= 2;
  const abMultValue = Number.parseFloat(abMult);
  const abMultValid = Number.isFinite(abMultValue) && abMultValue > 0;
  const atrBandParamsValid = !isAtrBand || (abWindowValid && abMultValid);

  // ADX thresholds are on the 0–100 DI scale (exclusive); periods are integers ≥ 2.
  const adxPeriodValue = Number.parseInt(adxPeriod, 10);
  const adxPeriodValid = Number.isInteger(adxPeriodValue) && adxPeriodValue >= 2;
  const adxThresholdValue = Number.parseFloat(adxThreshold);
  const adxThresholdValid =
    Number.isFinite(adxThresholdValue) && adxThresholdValue > 0 && adxThresholdValue < 100;
  const adxParamsValid = !isAdx || (adxPeriodValid && adxThresholdValid);
  // MACD periods are integers; the slow EMA must be longer than the fast one.
  const macdFastValue = Number.parseInt(macdFast, 10);
  const macdSlowValue = Number.parseInt(macdSlow, 10);
  const macdSignalValue = Number.parseInt(macdSignal, 10);
  const macdFastValid = Number.isInteger(macdFastValue) && macdFastValue >= 2;
  const macdSlowValid = Number.isInteger(macdSlowValue) && macdSlowValue >= 3;
  const macdSignalValid = Number.isInteger(macdSignalValue) && macdSignalValue >= 2;
  const macdOrdered = macdFastValid && macdSlowValid && macdSlowValue > macdFastValue;
  const macdParamsValid = !isMacd || (macdOrdered && macdSignalValid);
  const haWindowValue = Number.parseInt(haVolumeWindow, 10);
  const haWindowValid = Number.isInteger(haWindowValue) && haWindowValue >= 2;
  const haParamsValid = !isHeikinAshi || !haVolumeFilter || haWindowValid;
  const hmaFastValue = Number.parseInt(hmaFast, 10);
  const hmaSlowValue = Number.parseInt(hmaSlow, 10);
  const hmaFastValid = Number.isInteger(hmaFastValue) && hmaFastValue >= 2;
  const hmaSlowValid = Number.isInteger(hmaSlowValue) && hmaSlowValue >= 3;
  const hmaOrdered = hmaFastValid && hmaSlowValid && hmaSlowValue > hmaFastValue;
  const hmaParamsValid = !isHma || hmaOrdered;
  const ribbonFastValue = Number.parseInt(ribbonFast, 10);
  const ribbonMidValue = Number.parseInt(ribbonMid, 10);
  const ribbonSlowValue = Number.parseInt(ribbonSlow, 10);
  const ribbonIntegers =
    Number.isInteger(ribbonFastValue) &&
    Number.isInteger(ribbonMidValue) &&
    Number.isInteger(ribbonSlowValue) &&
    ribbonFastValue >= 1;
  // The ribbon periods must increase strictly: fast < mid < slow.
  const ribbonOrdered =
    ribbonIntegers && ribbonFastValue < ribbonMidValue && ribbonMidValue < ribbonSlowValue;
  const ribbonParamsValid = !isRibbon || ribbonOrdered;
  const vamaLookbackValue = Number.parseInt(vamaLookback, 10);
  const vamaAlphaMinValue = Number.parseFloat(vamaAlphaMin);
  const vamaAlphaMaxValue = Number.parseFloat(vamaAlphaMax);
  const vamaLookbackValid = Number.isInteger(vamaLookbackValue) && vamaLookbackValue >= 2;
  const vamaAlphaInRange = (v: number) => Number.isFinite(v) && v > 0 && v <= 1;
  // The smoothing range must be valid and ordered: 0 < α min < α max ≤ 1.
  const vamaAlphasValid =
    vamaAlphaInRange(vamaAlphaMinValue) &&
    vamaAlphaInRange(vamaAlphaMaxValue) &&
    vamaAlphaMinValue < vamaAlphaMaxValue;
  const vamaParamsValid = !isVama || (vamaLookbackValid && vamaAlphasValid);
  const pvThresholdFraction = Number.parseFloat(pvThresholdPct) / 100;
  const pvThresholdValid =
    Number.isFinite(pvThresholdFraction) && pvThresholdFraction > 0 && pvThresholdFraction < 1;
  const velocityParamsValid = !isVelocity || pvThresholdValid;
  const tcInt = (value: string, min: number) => {
    const n = Number.parseInt(value, 10);
    return Number.isInteger(n) && n >= min ? n : null;
  };
  const tcNum = (value: string) => {
    const n = Number.parseFloat(value);
    return Number.isFinite(n) ? n : null;
  };
  const tcValues = {
    smaFast: tcInt(tcSmaFast, 2),
    smaSlow: tcInt(tcSmaSlow, 3),
    macdFast: tcInt(tcMacdFast, 2),
    macdSlow: tcInt(tcMacdSlow, 3),
    macdSignal: tcInt(tcMacdSignal, 2),
    rsiPeriod: tcInt(tcRsiPeriod, 2),
    rsiEntry: tcNum(tcRsiEntry),
    rsiMax: tcNum(tcRsiMax),
    rsiExit: tcNum(tcRsiExit),
    rocPeriod: tcInt(tcRocPeriod, 1),
    obvWindow: tcInt(tcObvWindow, 1),
  };
  const tcSmaOrdered =
    tcValues.smaFast !== null && tcValues.smaSlow !== null && tcValues.smaFast < tcValues.smaSlow;
  const tcMacdOrdered =
    tcValues.macdFast !== null &&
    tcValues.macdSlow !== null &&
    tcValues.macdFast < tcValues.macdSlow;
  // RSI levels: 0 ≤ exit ≤ entry < cap ≤ 100 (the exit sits below the entry: hysteresis).
  const tcRsiOrdered =
    tcValues.rsiExit !== null &&
    tcValues.rsiEntry !== null &&
    tcValues.rsiMax !== null &&
    tcValues.rsiExit >= 0 &&
    tcValues.rsiExit <= tcValues.rsiEntry &&
    tcValues.rsiEntry < tcValues.rsiMax &&
    tcValues.rsiMax <= 100;
  const trendConfirmationValid =
    !isTrendConfirmation ||
    (tcSmaOrdered &&
      tcMacdOrdered &&
      tcValues.macdSignal !== null &&
      tcValues.rsiPeriod !== null &&
      tcRsiOrdered &&
      (!tcUseRoc || tcValues.rocPeriod !== null) &&
      (!tcUseObv || tcValues.obvWindow !== null));
  const raAdxLookbackValue = Number.parseInt(raAdxLookback, 10);
  const raAdxLookbackValid = Number.isInteger(raAdxLookbackValue) && raAdxLookbackValue >= 2;
  const raAdxThresholdValue = Number.parseFloat(raAdxThreshold);
  const raAdxThresholdValid =
    Number.isFinite(raAdxThresholdValue) && raAdxThresholdValue > 0 && raAdxThresholdValue < 100;
  const raAdxValid = !isReversion || !raAdxExit || (raAdxLookbackValid && raAdxThresholdValid);

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
    // The ADX danger exit is only sent when on, so presets without it still match.
    ...(raAdxExit
      ? {
          adx_exit: true,
          adx_lookback: raAdxLookbackValue,
          adx_threshold: raAdxThresholdValue,
        }
      : {}),
  };
  // SuperTrend presets omit exit_on_midline (it only applies to Keltner), so it is
  // sent for Keltner only — keeping the customized check exact against each preset.
  const atrBandParams: Record<string, unknown> =
    abVersion === 'keltner'
      ? {
          version: 'keltner',
          window: abWindowValue,
          atr_mult: abMultValue,
          exit_on_midline: abExitOnMidline,
        }
      : { version: 'supertrend', window: abWindowValue, atr_mult: abMultValue };
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
        : isAtrBand
          ? atrBandParams
          : isAdx
            ? { period: adxPeriodValue, threshold: adxThresholdValue }
            : isTrendConfirmation
              ? {
                  sma_fast: tcValues.smaFast,
                  sma_slow: tcValues.smaSlow,
                  macd_fast: tcValues.macdFast,
                  macd_slow: tcValues.macdSlow,
                  macd_signal: tcValues.macdSignal,
                  rsi_period: tcValues.rsiPeriod,
                  rsi_entry: tcValues.rsiEntry,
                  rsi_max: tcValues.rsiMax,
                  rsi_exit: tcValues.rsiExit,
                  use_roc: tcUseRoc,
                  roc_period: tcValues.rocPeriod,
                  use_obv: tcUseObv,
                  obv_window: tcValues.obvWindow,
                }
              : isVelocity
              ? { threshold_pct: pvThresholdFraction }
              : isVama
              ? {
                  lookback: vamaLookbackValue,
                  alpha_min: vamaAlphaMinValue,
                  alpha_max: vamaAlphaMaxValue,
                  adaptive: vamaAdaptive,
                }
              : isRibbon
              ? {
                  fast_period: ribbonFastValue,
                  mid_period: ribbonMidValue,
                  slow_period: ribbonSlowValue,
                }
              : isHma
              ? { fast_period: hmaFastValue, slow_period: hmaSlowValue }
              : isHeikinAshi
              ? haVolumeFilter
                ? { volume_filter: true, volume_window: haWindowValue }
                : { volume_filter: false }
              : isMacd
              ? {
                  fast_period: macdFastValue,
                  slow_period: macdSlowValue,
                  signal_period: macdSignalValue,
                }
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
    atrBandParamsValid &&
    adxParamsValid &&
    macdParamsValid &&
    haParamsValid &&
    hmaParamsValid &&
    ribbonParamsValid &&
    vamaParamsValid &&
    velocityParamsValid &&
    trendConfirmationValid &&
    raAdxValid &&
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
  const abWindowInvalid = isAtrBand && abWindow.length > 0 && !abWindowValid;
  const abMultInvalid = isAtrBand && abMult.length > 0 && !abMultValid;
  const adxPeriodInvalid = isAdx && adxPeriod.length > 0 && !adxPeriodValid;
  const macdFastInvalid = isMacd && macdFast.length > 0 && (!macdFastValid || !macdOrdered);
  const macdSlowInvalid = isMacd && macdSlow.length > 0 && (!macdSlowValid || !macdOrdered);
  const macdSignalInvalid = isMacd && macdSignal.length > 0 && !macdSignalValid;
  const tcFieldInvalid = (value: string, ok: boolean) =>
    isTrendConfirmation && value.length > 0 && !ok;
  const pvThresholdInvalid = isVelocity && pvThresholdPct.length > 0 && !pvThresholdValid;
  const vamaLookbackInvalid = isVama && vamaLookback.length > 0 && !vamaLookbackValid;
  const vamaAlphaInvalid = (value: string) => isVama && value.length > 0 && !vamaAlphasValid;
  const ribbonInvalid = (value: string) => isRibbon && value.length > 0 && !ribbonOrdered;
  const hmaFastInvalid = isHma && hmaFast.length > 0 && (!hmaFastValid || !hmaOrdered);
  const hmaSlowInvalid = isHma && hmaSlow.length > 0 && (!hmaSlowValid || !hmaOrdered);
  const haWindowInvalid =
    isHeikinAshi && haVolumeFilter && haVolumeWindow.length > 0 && !haWindowValid;
  const adxThresholdInvalid = isAdx && adxThreshold.length > 0 && !adxThresholdValid;
  const raAdxLookbackInvalid = raAdxExit && raAdxLookback.length > 0 && !raAdxLookbackValid;
  const raAdxThresholdInvalid =
    raAdxExit && raAdxThreshold.length > 0 && !raAdxThresholdValid;
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
            ) : isAtrBand ? (
              <div className="flex flex-col gap-3">
                <div>
                  <label
                    htmlFor="bot-atr-band-version"
                    className="block text-sm font-medium text-slate-700"
                  >
                    Version
                  </label>
                  <select
                    id="bot-atr-band-version"
                    value={abVersion}
                    onChange={(e) =>
                      handleAtrBandVersionChange(e.target.value as AtrBandVersion)
                    }
                    className={FIELD_CLASS}
                  >
                    <option value="supertrend">SuperTrend</option>
                    <option value="keltner">Keltner channel</option>
                  </select>
                  <p className="mt-1 text-xs text-slate-500">
                    {abVersion === 'supertrend'
                      ? 'Buys in an up-trend above the SuperTrend line; the exit is left to the risk controls below.'
                      : 'Buys on a break above the upper band; optionally sells back below the moving average.'}
                  </p>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <NumberField
                    id="bot-atr-band-window"
                    label="Window"
                    min={2}
                    step={1}
                    value={abWindow}
                    onChange={setAbWindow}
                    hint="Bars in the rolling window the bands are measured over."
                    invalid={abWindowInvalid}
                  />
                  <NumberField
                    id="bot-atr-band-mult"
                    label="ATR multiplier (×)"
                    min={0.1}
                    step={0.1}
                    value={abMult}
                    onChange={setAbMult}
                    hint="Band distance from the midline, in multiples of ATR."
                    invalid={abMultInvalid}
                  />
                </div>
                {abVersion === 'keltner' && (
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={abExitOnMidline}
                      onChange={(e) => setAbExitOnMidline(e.target.checked)}
                    />
                    Exit when the close falls below the moving average
                  </label>
                )}
              </div>
            ) : isTrendConfirmation ? (
              <div className="flex flex-col gap-4">
                <p className="text-xs text-slate-500">
                  Buys only when every check below agrees; sells as soon as one fails.
                </p>
                <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <legend className="mb-1 text-sm font-medium text-slate-700">
                    Trend — fast SMA above slow SMA
                  </legend>
                  <NumberField
                    id="bot-tc-sma-fast"
                    label="Fast SMA"
                    min={2}
                    step={1}
                    value={tcSmaFast}
                    onChange={setTcSmaFast}
                    hint="Must be below the slow SMA."
                    invalid={tcFieldInvalid(tcSmaFast, tcSmaOrdered)}
                  />
                  <NumberField
                    id="bot-tc-sma-slow"
                    label="Slow SMA"
                    min={3}
                    step={1}
                    value={tcSmaSlow}
                    onChange={setTcSmaSlow}
                    hint="Must be above the fast SMA."
                    invalid={tcFieldInvalid(tcSmaSlow, tcSmaOrdered)}
                  />
                </fieldset>
                <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <legend className="mb-1 text-sm font-medium text-slate-700">
                    Momentum — MACD histogram above 0
                  </legend>
                  <NumberField
                    id="bot-tc-macd-fast"
                    label="MACD fast"
                    min={2}
                    step={1}
                    value={tcMacdFast}
                    onChange={setTcMacdFast}
                    hint="Fast EMA; below the slow one."
                    invalid={tcFieldInvalid(tcMacdFast, tcMacdOrdered)}
                  />
                  <NumberField
                    id="bot-tc-macd-slow"
                    label="MACD slow"
                    min={3}
                    step={1}
                    value={tcMacdSlow}
                    onChange={setTcMacdSlow}
                    hint="Slow EMA; above the fast one."
                    invalid={tcFieldInvalid(tcMacdSlow, tcMacdOrdered)}
                  />
                  <NumberField
                    id="bot-tc-macd-signal"
                    label="MACD signal"
                    min={2}
                    step={1}
                    value={tcMacdSignal}
                    onChange={setTcMacdSignal}
                    hint="Signal-line EMA."
                    invalid={tcFieldInvalid(tcMacdSignal, tcValues.macdSignal !== null)}
                  />
                </fieldset>
                <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-4">
                  <legend className="mb-1 text-sm font-medium text-slate-700">
                    Strength — RSI strong but not overheated
                  </legend>
                  <NumberField
                    id="bot-tc-rsi-period"
                    label="RSI period"
                    min={2}
                    step={1}
                    value={tcRsiPeriod}
                    onChange={setTcRsiPeriod}
                    hint="Bars in the RSI."
                    invalid={tcFieldInvalid(tcRsiPeriod, tcValues.rsiPeriod !== null)}
                  />
                  <NumberField
                    id="bot-tc-rsi-entry"
                    label="RSI entry above"
                    min={0}
                    step={1}
                    value={tcRsiEntry}
                    onChange={setTcRsiEntry}
                    hint="Buys only above this."
                    invalid={tcFieldInvalid(tcRsiEntry, tcRsiOrdered)}
                  />
                  <NumberField
                    id="bot-tc-rsi-max"
                    label="RSI cap"
                    min={1}
                    step={1}
                    value={tcRsiMax}
                    onChange={setTcRsiMax}
                    hint="No new buys at or above it."
                    invalid={tcFieldInvalid(tcRsiMax, tcRsiOrdered)}
                  />
                  <NumberField
                    id="bot-tc-rsi-exit"
                    label="RSI exit below"
                    min={0}
                    step={1}
                    value={tcRsiExit}
                    onChange={setTcRsiExit}
                    hint="Sells below this; at most the entry level."
                    invalid={tcFieldInvalid(tcRsiExit, tcRsiOrdered)}
                  />
                </fieldset>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="flex flex-col gap-2">
                    <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                      <input
                        type="checkbox"
                        checked={tcUseRoc}
                        onChange={(e) => setTcUseRoc(e.target.checked)}
                      />
                      Also require a positive rate of change
                    </label>
                    {tcUseRoc && (
                      <NumberField
                        id="bot-tc-roc-period"
                        label="ROC period (bars)"
                        min={1}
                        step={1}
                        value={tcRocPeriod}
                        onChange={setTcRocPeriod}
                        hint="Price must be higher than this many bars ago."
                        invalid={tcFieldInvalid(tcRocPeriod, tcValues.rocPeriod !== null)}
                      />
                    )}
                  </div>
                  <div className="flex flex-col gap-2">
                    <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                      <input
                        type="checkbox"
                        checked={tcUseObv}
                        onChange={(e) => setTcUseObv(e.target.checked)}
                      />
                      Also require rising on-balance volume
                    </label>
                    {tcUseObv && (
                      <NumberField
                        id="bot-tc-obv-window"
                        label="OBV window (bars)"
                        min={1}
                        step={1}
                        value={tcObvWindow}
                        onChange={setTcObvWindow}
                        hint="Volume must back the move over this many bars."
                        invalid={tcFieldInvalid(tcObvWindow, tcValues.obvWindow !== null)}
                      />
                    )}
                  </div>
                </div>
              </div>
            ) : isVelocity ? (
              <NumberField
                id="bot-velocity-threshold"
                label="Velocity threshold (% per bar)"
                min={0.01}
                step={0.01}
                value={pvThresholdPct}
                onChange={setPvThresholdPct}
                hint="Buys once a bar falls more than this, by less than the bar before; sells on the first up-bar."
                invalid={pvThresholdInvalid}
              />
            ) : isVama ? (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <NumberField
                    id="bot-vama-lookback"
                    label="Lookback (bars)"
                    min={2}
                    step={1}
                    value={vamaLookback}
                    onChange={setVamaLookback}
                    hint="Bars the volatility is measured over."
                    invalid={vamaLookbackInvalid}
                  />
                  <NumberField
                    id="bot-vama-alpha-min"
                    label="Smoothing min (α)"
                    min={0.01}
                    step={0.01}
                    value={vamaAlphaMin}
                    onChange={setVamaAlphaMin}
                    hint="Slowest speed (0–1). Must be below the max."
                    invalid={vamaAlphaInvalid(vamaAlphaMin)}
                  />
                  <NumberField
                    id="bot-vama-alpha-max"
                    label="Smoothing max (α)"
                    min={0.01}
                    step={0.01}
                    value={vamaAlphaMax}
                    onChange={setVamaAlphaMax}
                    hint="Fastest speed (0–1). Used whenever smoothing is fixed."
                    invalid={vamaAlphaInvalid(vamaAlphaMax)}
                  />
                </div>
                <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={vamaAdaptive}
                    onChange={(e) => setVamaAdaptive(e.target.checked)}
                  />
                  Adaptive smoothing (faster when volatile, slower when calm)
                </label>
              </div>
            ) : isRibbon ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <NumberField
                  id="bot-ribbon-fast"
                  label="Fast SMA"
                  min={1}
                  step={1}
                  value={ribbonFast}
                  onChange={setRibbonFast}
                  hint="Bars in the fast average. Must be below the mid SMA."
                  invalid={ribbonInvalid(ribbonFast)}
                />
                <NumberField
                  id="bot-ribbon-mid"
                  label="Mid SMA"
                  min={2}
                  step={1}
                  value={ribbonMid}
                  onChange={setRibbonMid}
                  hint="Bars in the middle average. Between the fast and slow SMA."
                  invalid={ribbonInvalid(ribbonMid)}
                />
                <NumberField
                  id="bot-ribbon-slow"
                  label="Slow SMA"
                  min={3}
                  step={1}
                  value={ribbonSlow}
                  onChange={setRibbonSlow}
                  hint="Bars in the slow average. Must be above the mid SMA."
                  invalid={ribbonInvalid(ribbonSlow)}
                />
              </div>
            ) : isHma ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <NumberField
                  id="bot-hma-fast"
                  label="Fast HMA"
                  min={2}
                  step={1}
                  value={hmaFast}
                  onChange={setHmaFast}
                  hint="Bars in the fast Hull Moving Average. Must be below the slow HMA."
                  invalid={hmaFastInvalid}
                />
                <NumberField
                  id="bot-hma-slow"
                  label="Slow HMA"
                  min={3}
                  step={1}
                  value={hmaSlow}
                  onChange={setHmaSlow}
                  hint="Bars in the slow Hull Moving Average. Must be above the fast HMA."
                  invalid={hmaSlowInvalid}
                />
              </div>
            ) : isHeikinAshi ? (
              <div className="flex flex-col gap-3">
                <p className="text-xs text-slate-500">
                  Buys on a green Heikin-Ashi candle and sells on the first red one.
                </p>
                <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={haVolumeFilter}
                    onChange={(e) => setHaVolumeFilter(e.target.checked)}
                  />
                  Require above-average volume (and sell when it fades)
                </label>
                {haVolumeFilter && (
                  <NumberField
                    id="bot-ha-volume-window"
                    label="Volume window (bars)"
                    min={2}
                    step={1}
                    value={haVolumeWindow}
                    onChange={setHaVolumeWindow}
                    hint="Bars the average volume is measured over (the current bar included)."
                    invalid={haWindowInvalid}
                  />
                )}
              </div>
            ) : isMacd ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <NumberField
                  id="bot-macd-fast"
                  label="Fast EMA"
                  min={2}
                  step={1}
                  value={macdFast}
                  onChange={setMacdFast}
                  hint="Bars in the fast moving average. Must be below the slow EMA."
                  invalid={macdFastInvalid}
                />
                <NumberField
                  id="bot-macd-slow"
                  label="Slow EMA"
                  min={3}
                  step={1}
                  value={macdSlow}
                  onChange={setMacdSlow}
                  hint="Bars in the slow moving average. Must be above the fast EMA."
                  invalid={macdSlowInvalid}
                />
                <NumberField
                  id="bot-macd-signal"
                  label="Signal EMA"
                  min={2}
                  step={1}
                  value={macdSignal}
                  onChange={setMacdSignal}
                  hint="Bars in the signal line that smooths the MACD."
                  invalid={macdSignalInvalid}
                />
              </div>
            ) : isAdx ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <NumberField
                  id="bot-adx-period"
                  label="ADX period"
                  min={2}
                  step={1}
                  value={adxPeriod}
                  onChange={setAdxPeriod}
                  hint="Bars in each directional-movement sum and in the ADX average."
                  invalid={adxPeriodInvalid}
                />
                <NumberField
                  id="bot-adx-threshold"
                  label="ADX threshold"
                  min={1}
                  step={1}
                  value={adxThreshold}
                  onChange={setAdxThreshold}
                  hint="Buys above it (with +DI leading); sells once the ADX drops below."
                  invalid={adxThresholdInvalid}
                />
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
                          ? 'Sell once back within this of the average. At most the entry.'
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
                          ? 'Sell once back above this many std devs below. At most the entry.'
                          : 'Unused while exits go via take-profit / stop-loss.'
                      }
                      invalid={raExitZInvalid}
                    />
                  </>
                )}
                <div className="flex flex-col gap-3 sm:col-span-2">
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={raAdxExit}
                      onChange={(e) => setRaAdxExit(e.target.checked)}
                    />
                    ADX danger exit: sell a losing trade in a strong downtrend
                  </label>
                  {raAdxExit && (
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <NumberField
                        id="bot-ra-adx-lookback"
                        label="ADX lookback (bars)"
                        min={2}
                        step={1}
                        value={raAdxLookback}
                        onChange={setRaAdxLookback}
                        hint="Bars the directional strength is measured over."
                        invalid={raAdxLookbackInvalid}
                      />
                      <NumberField
                        id="bot-ra-adx-threshold"
                        label="ADX danger threshold"
                        min={1}
                        step={1}
                        value={raAdxThreshold}
                        onChange={setRaAdxThreshold}
                        hint="Sells when the strength is above this and −DI leads +DI."
                        invalid={raAdxThresholdInvalid}
                      />
                    </div>
                  )}
                </div>
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
