import type { EChartsCoreOption } from 'echarts/core';

/** Parameters used by the illustrative chart (not the live defaults). */
const LOOKBACK = 4;
const ALPHA_MIN = 0.02;
const ALPHA_MAX = 0.3;

/**
 * A fixed, deterministic synthetic close series: a calm drift lower, a sharp rally, then a
 * slide back. Purely illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  101, 100.9, 100.8, 100.7, 100.6, 100.5, 100.4, 100.3, 102, 104.5, 107, 109, 110.5,
  110, 108.5, 106.5, 104.5, 103, 102, 101.5,
] as const;

function pstd(values: readonly number[]): number {
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  return Math.sqrt(values.reduce((a, v) => a + (v - mean) ** 2, 0) / values.length);
}

/** Smoothing factor per bar (null while undefined) — mirrors the backend helper. */
export function smoothingFactors(adaptive: boolean): (number | null)[] {
  const n = LOOKBACK;
  const vols = SYNTHETIC_PRICES.map((_, i) =>
    i >= n - 1 ? pstd(SYNTHETIC_PRICES.slice(i - n + 1, i + 1)) : null,
  );
  return vols.map((vol, i) => {
    if (vol == null) return null;
    if (!adaptive) return vol > 0 ? ALPHA_MAX : ALPHA_MIN;
    if (i < 2 * n - 2) return null;
    const window = vols.slice(i - n + 1, i + 1) as number[];
    const average = window.reduce((a, b) => a + b, 0) / window.length;
    if (average <= 0) return ALPHA_MIN;
    return Math.min(ALPHA_MAX, Math.max(ALPHA_MIN, (ALPHA_MAX * vol) / average));
  });
}

/** VAMA per bar, starting at the first bar with a defined smoothing factor. */
export function vamaSeries(adaptive: boolean): (number | null)[] {
  const alphas = smoothingFactors(adaptive);
  let value: number | null = null;
  return SYNTHETIC_PRICES.map((close, i) => {
    const alpha = alphas[i];
    if (alpha == null) return null;
    value = value == null ? close : alpha * close + (1 - alpha) * value;
    return value;
  });
}

/** An entry/exit signal with the x-index it occurs at. */
export interface VamaSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/** Entry on a close above the fixed-smoothing VAMA, exit at or below it. */
export function vamaSignals(): VamaSignal[] {
  const line = vamaSeries(false);
  const signals: VamaSignal[] = [];
  let holding = false;
  SYNTHETIC_PRICES.forEach((close, index) => {
    const v = line[index];
    if (v == null) return;
    if (!holding && close > v) {
      signals.push({ index, kind: 'entry' });
      holding = true;
    } else if (holding && close <= v) {
      signals.push({ index, kind: 'exit' });
      holding = false;
    }
  });
  return signals;
}

/**
 * Build the ECharts option for the illustrative VAMA chart: the synthetic close, the
 * fixed-smoothing (course) VAMA and the adaptive VAMA, with entry / exit mark-lines for
 * the fixed one. Deterministic and self-contained.
 */
export function buildVamaChartOption(): EChartsCoreOption {
  const marks = vamaSignals().map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));
  return {
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    legend: { data: ['Price', 'VAMA (fixed)', 'VAMA (adaptive)'], top: 0 },
    xAxis: { type: 'category', data: SYNTHETIC_PRICES.map((_, i) => String(i)), boundaryGap: false },
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
      },
      {
        id: 'vama-fixed',
        name: 'VAMA (fixed)',
        type: 'line',
        showSymbol: false,
        itemStyle: { color: '#d97706' },
        data: vamaSeries(false),
      },
      {
        id: 'vama-adaptive',
        name: 'VAMA (adaptive)',
        type: 'line',
        showSymbol: false,
        lineStyle: { type: 'dashed' },
        itemStyle: { color: '#7c3aed' },
        data: vamaSeries(true),
      },
    ],
  };
}
