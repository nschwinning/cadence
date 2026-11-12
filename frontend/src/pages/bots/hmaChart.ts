import type { EChartsCoreOption } from 'echarts/core';

/** HMA periods used by the illustrative chart (not the live defaults). */
const FAST = 4;
const SLOW = 9;

/**
 * A fixed, deterministic synthetic close series: a slide, an accelerating rally (the
 * fast HMA rises above the slow one → entry), then a roll-over into a decline (fast
 * falls below slow while dropping → exit). Purely illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100.5, 100.5, 101, 102, 103.5,
  105.5, 108, 111, 114, 116.5, 118, 118.5, 118, 116.5, 114, 111, 108, 105,
] as const;

/** Linearly weighted mean of the latest `period` values (latest heaviest). */
export function wma(values: readonly number[], period: number): number {
  const window = values.slice(-period);
  const weighted = window.reduce((sum, v, i) => sum + v * (i + 1), 0);
  return weighted / ((period * (period + 1)) / 2);
}

/** Proper Hull Moving Average at the latest value, or null if too short. */
export function hma(values: readonly number[], period: number): number | null {
  const smoothing = Math.floor(Math.sqrt(period));
  const half = Math.floor(period / 2);
  if (values.length < period + smoothing - 1) return null;
  const raw: number[] = [];
  for (let end = values.length - smoothing + 1; end <= values.length; end += 1) {
    const upTo = values.slice(0, end);
    raw.push(2 * wma(upTo, half) - wma(upTo, period));
  }
  return wma(raw, smoothing);
}

/** Per-bar HMA series (null until enough history). */
export function hmaSeries(period: number): (number | null)[] {
  return SYNTHETIC_PRICES.map((_, i) => hma(SYNTHETIC_PRICES.slice(0, i + 1), period));
}

/** An entry/exit signal with the x-index it occurs at. */
export interface HmaSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/** Entry on a rising fast HMA above the slow one; exit on a falling fast HMA below it. */
export function hmaSignals(): HmaSignal[] {
  const fast = hmaSeries(FAST);
  const slow = hmaSeries(SLOW);
  const signals: HmaSignal[] = [];
  let holding = false;
  for (let i = 1; i < SYNTHETIC_PRICES.length; i += 1) {
    const f = fast[i];
    const s = slow[i];
    const prev = fast[i - 1];
    if (f == null || s == null || prev == null) continue;
    const slope = f - prev;
    if (!holding && f > s && slope > 0) {
      signals.push({ index: i, kind: 'entry' });
      holding = true;
    } else if (holding && f < s && slope < 0) {
      signals.push({ index: i, kind: 'exit' });
      holding = false;
    }
  }
  return signals;
}

/**
 * Build the ECharts option for the illustrative HMA Trend chart: the synthetic close,
 * the fast and slow Hull Moving Averages, and vertical mark-lines at the entry and exit.
 * Deterministic and self-contained.
 */
export function buildHmaChartOption(): EChartsCoreOption {
  const marks = hmaSignals().map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));
  return {
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    legend: { data: ['Price', 'Fast HMA', 'Slow HMA'], top: 0 },
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
        id: 'fast-hma',
        name: 'Fast HMA',
        type: 'line',
        showSymbol: false,
        itemStyle: { color: '#059669' },
        data: hmaSeries(FAST),
      },
      {
        id: 'slow-hma',
        name: 'Slow HMA',
        type: 'line',
        showSymbol: false,
        lineStyle: { type: 'dashed' },
        itemStyle: { color: '#dc2626' },
        data: hmaSeries(SLOW),
      },
    ],
  };
}
