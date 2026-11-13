import type { EChartsCoreOption } from 'echarts/core';

/** Illustrative parameters: ATR / HL2 window, SMA period, baseline bars. */
const ATR_WINDOW = 4;
const SMA_PERIOD = 4;
const BASELINE_BARS = 8;

/**
 * A fixed, deterministic synthetic close series: a choppy warm-up, a calm climb (trend
 * mode) and a volatile dip and snap-back (reversion mode). Purely illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  100, 101.5, 99.8, 101.2, 100, 101.4, 100.2, 101, 101.2, 101.5, 101.7, 102, 102.3, 102.5,
  102.4, 102.1, 101.6, 101.2, 103.6,
] as const;

const FIRST = BASELINE_BARS + ATR_WINDOW - 1;

function meanAbsChange(values: readonly number[]): number {
  let total = 0;
  for (let i = 1; i < values.length; i += 1) total += Math.abs(values[i] - values[i - 1]);
  return total / (values.length - 1);
}

function atrAt(i: number): number {
  return meanAbsChange(SYNTHETIC_PRICES.slice(i - ATR_WINDOW + 1, i + 1));
}

/** Per bar: its regime plus HL2 and SMA, or nulls before enough history. */
export function regimeSeries(): {
  regime: 'trend' | 'reversion' | null;
  hl2: number | null;
  sma: number | null;
}[] {
  return SYNTHETIC_PRICES.map((_, i) => {
    if (i < FIRST) return { regime: null, hl2: null, sma: null };
    let baseline = 0;
    for (let j = i - BASELINE_BARS + 1; j <= i; j += 1) baseline += atrAt(j);
    baseline /= BASELINE_BARS;
    const window = SYNTHETIC_PRICES.slice(i - ATR_WINDOW + 1, i + 1);
    const smaWindow = SYNTHETIC_PRICES.slice(i - SMA_PERIOD + 1, i + 1);
    return {
      regime: atrAt(i) <= baseline ? 'trend' : 'reversion',
      hl2: (Math.max(...window) + Math.min(...window)) / 2,
      sma: smaWindow.reduce((a, b) => a + b, 0) / SMA_PERIOD,
    };
  });
}

/** An entry/exit signal with the x-index and regime it occurs in. */
export interface RegimeSignal {
  index: number;
  kind: 'entry' | 'exit';
  regime: 'trend' | 'reversion';
}

/** Trend: above HL2 in, below out. Reversion: below the SMA in, back at it out. */
export function regimeSignals(): RegimeSignal[] {
  const rows = regimeSeries();
  const signals: RegimeSignal[] = [];
  let holding = false;
  rows.forEach(({ regime, hl2, sma }, index) => {
    if (regime === null || hl2 === null || sma === null) return;
    const close = SYNTHETIC_PRICES[index];
    const enter = regime === 'trend' ? close > hl2 : close < sma;
    const exit = regime === 'trend' ? close < hl2 : close >= sma;
    if (!holding && enter) {
      signals.push({ index, kind: 'entry', regime });
      holding = true;
    } else if (holding && exit) {
      signals.push({ index, kind: 'exit', regime });
      holding = false;
    }
  });
  return signals;
}

/** Contiguous runs of the volatile (reversion) regime, as [start, end] indices. */
function volatileRuns(): [number, number][] {
  const runs: [number, number][] = [];
  regimeSeries().forEach(({ regime }, i) => {
    if (regime !== 'reversion') return;
    const last = runs[runs.length - 1];
    if (last && last[1] === i - 1) last[1] = i;
    else runs.push([i, i]);
  });
  return runs;
}

/**
 * Build the ECharts option for the illustrative Volatility Regime Switcher chart: the
 * synthetic close with HL2 and the SMA, volatile stretches shaded, and vertical mark-lines
 * at each entry and exit. Deterministic and self-contained.
 */
export function buildVolatilityRegimeChartOption(): EChartsCoreOption {
  const rows = regimeSeries();
  const marks = regimeSignals().map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));
  return {
    grid: { left: 48, right: 24, top: 32, bottom: 28 },
    legend: { data: ['Price', 'HL2 (calm)', 'SMA (volatile)'], top: 0 },
    xAxis: {
      type: 'category',
      data: SYNTHETIC_PRICES.map((_, i) => String(i)),
      boundaryGap: false,
    },
    yAxis: { type: 'value', scale: true },
    series: [
      {
        id: 'price',
        name: 'Price',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: '#2563eb' },
        data: SYNTHETIC_PRICES.slice(),
        markLine: { symbol: 'none', data: marks },
        markArea: {
          itemStyle: { color: 'rgba(245, 158, 11, 0.12)' },
          data: volatileRuns().map(([start, end]) => [
            { xAxis: String(start), name: 'Volatile' },
            { xAxis: String(end) },
          ]),
        },
      },
      {
        id: 'hl2',
        name: 'HL2 (calm)',
        type: 'line',
        showSymbol: false,
        lineStyle: { type: 'dashed', width: 1 },
        itemStyle: { color: '#059669' },
        data: rows.map((r) => r.hl2),
      },
      {
        id: 'sma',
        name: 'SMA (volatile)',
        type: 'line',
        showSymbol: false,
        lineStyle: { type: 'dotted', width: 1 },
        itemStyle: { color: '#f59e0b' },
        data: rows.map((r) => r.sma),
      },
    ],
  };
}
