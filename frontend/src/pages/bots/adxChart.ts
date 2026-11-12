import type { EChartsCoreOption } from 'echarts/core';

/** Period and threshold used by the illustrative chart (not the live defaults). */
const PERIOD = 4;
const THRESHOLD = 20;

interface SyntheticBar {
  high: number;
  low: number;
  close: number;
}

/**
 * A fixed, deterministic synthetic bar series: choppy sideways bars, a clean
 * up-trend (ADX climbs above the threshold → entry), then chop again (ADX fades
 * below the threshold → exit). Purely illustrative, not market data.
 */
const SYNTHETIC_BARS: SyntheticBar[] = [
  ...Array.from({ length: 8 }, (_, i) =>
    i % 2 === 0 ? { high: 102, low: 100, close: 101 } : { high: 101, low: 99, close: 100 },
  ),
  ...Array.from({ length: 8 }, (_, i) => ({
    high: 104 + 2 * i,
    low: 102 + 2 * i,
    close: 103.5 + 2 * i,
  })),
  ...Array.from({ length: 10 }, (_, i) =>
    i % 2 === 0 ? { high: 120, low: 118, close: 119 } : { high: 119, low: 117, close: 118 },
  ),
];

/** True range, +DM and −DM for each bar after the first (mirrors the backend helper). */
function directionalMovement(bars: readonly SyntheticBar[]) {
  const tr: number[] = [];
  const plus: number[] = [];
  const minus: number[] = [];
  for (let i = 1; i < bars.length; i += 1) {
    const up = bars[i].high - bars[i - 1].high;
    const down = bars[i - 1].low - bars[i].low;
    tr.push(
      Math.max(
        bars[i].high - bars[i].low,
        Math.abs(bars[i].high - bars[i - 1].close),
        Math.abs(bars[i].low - bars[i - 1].close),
      ),
    );
    plus.push(up > down && up > 0 ? up : 0);
    minus.push(down > up && down > 0 ? down : 0);
  }
  return { tr, plus, minus };
}

/** Per-bar ADX (null until two periods of bars exist), course style: plain sums. */
export function adxSeries(): (number | null)[] {
  const { tr, plus, minus } = directionalMovement(SYNTHETIC_BARS);
  const dx: number[] = [];
  for (let i = 0; i + PERIOD <= tr.length; i += 1) {
    const sum = (xs: number[]) => xs.slice(i, i + PERIOD).reduce((a, b) => a + b, 0);
    const trSum = sum(tr);
    const pdi = trSum > 0 ? (100 * sum(plus)) / trSum : 0;
    const mdi = trSum > 0 ? (100 * sum(minus)) / trSum : 0;
    dx.push(pdi + mdi > 0 ? (100 * Math.abs(pdi - mdi)) / (pdi + mdi) : 0);
  }
  // dx[k] covers bars k..k+PERIOD; the ADX at bar b averages the PERIOD dx values ending there.
  return SYNTHETIC_BARS.map((_, b) => {
    const last = b - PERIOD; // index of the dx window ending at bar b
    if (last < PERIOD - 1) return null;
    const window = dx.slice(last - PERIOD + 1, last + 1);
    return window.reduce((a, v) => a + v, 0) / PERIOD;
  });
}

/** An entry/exit signal with the x-index it occurs at. */
export interface AdxSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/** Entry when the ADX rises above the threshold while flat, exit when it falls below. */
export function adxSignals(): AdxSignal[] {
  const series = adxSeries();
  const signals: AdxSignal[] = [];
  let holding = false;
  series.forEach((value, index) => {
    if (value == null) return;
    if (!holding && value > THRESHOLD) {
      signals.push({ index, kind: 'entry' });
      holding = true;
    } else if (holding && value < THRESHOLD) {
      signals.push({ index, kind: 'exit' });
      holding = false;
    }
  });
  return signals;
}

/**
 * Build the ECharts option for the illustrative ADX Trend Strength chart: the
 * synthetic close line on the left axis, the ADX and its threshold on a 0–100 right
 * axis, and vertical mark-lines at the entry and exit. Deterministic and self-contained.
 */
export function buildAdxChartOption(): EChartsCoreOption {
  const x = SYNTHETIC_BARS.map((_, i) => String(i));
  const marks = adxSignals().map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));
  return {
    grid: { left: 48, right: 48, top: 24, bottom: 28 },
    legend: { data: ['Price', 'ADX'], top: 0 },
    xAxis: { type: 'category', data: x, boundaryGap: false },
    yAxis: [
      { type: 'value', scale: true },
      { type: 'value', min: 0, max: 100 },
    ],
    series: [
      {
        id: 'price',
        name: 'Price',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: '#2563eb' },
        data: SYNTHETIC_BARS.map((b) => b.close),
        markLine: { symbol: 'none', data: marks },
      },
      {
        id: 'adx',
        name: 'ADX',
        type: 'line',
        yAxisIndex: 1,
        showSymbol: false,
        lineStyle: { width: 1 },
        itemStyle: { color: '#7c3aed' },
        data: adxSeries(),
        markLine: {
          symbol: 'none',
          data: [{ yAxis: THRESHOLD, label: { formatter: 'Threshold' } }],
          lineStyle: { type: 'dashed', color: '#64748b' },
        },
      },
    ],
  };
}
