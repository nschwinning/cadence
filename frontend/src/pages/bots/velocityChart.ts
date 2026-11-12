import type { EChartsCoreOption } from 'echarts/core';

/** Threshold used by the illustrative chart (fraction of price per bar). */
const THRESHOLD = 0.004;

/**
 * A fixed, deterministic synthetic close series: a steady level, a sharp sell-off that
 * slows down (entry), and the first up-bar (exit). Purely illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  100, 100.2, 100.1, 100.3, 100.2, 99, 97.5, 96.6, 96.1, 96.9, 97.6, 98.1,
] as const;

/** Fractional change of each close from the previous one (null for the first). */
export function velocities(): (number | null)[] {
  return SYNTHETIC_PRICES.map((close, i) =>
    i === 0 ? null : (close - SYNTHETIC_PRICES[i - 1]) / SYNTHETIC_PRICES[i - 1],
  );
}

/** An entry/exit signal with the x-index it occurs at. */
export interface VelocitySignal {
  index: number;
  kind: 'entry' | 'exit';
}

/** Entry on a sharp but decelerating drop; exit on the first positive velocity. */
export function velocitySignals(): VelocitySignal[] {
  const v = velocities();
  const signals: VelocitySignal[] = [];
  let holding = false;
  for (let i = 2; i < SYNTHETIC_PRICES.length; i += 1) {
    const velocity = v[i]!;
    const acceleration = velocity - v[i - 1]!;
    if (!holding && velocity < -THRESHOLD && acceleration > 0) {
      signals.push({ index: i, kind: 'entry' });
      holding = true;
    } else if (holding && velocity > 0) {
      signals.push({ index: i, kind: 'exit' });
      holding = false;
    }
  }
  return signals;
}

/**
 * Build the ECharts option for the illustrative Price Velocity Reversal chart: the
 * synthetic close on the left axis, its per-bar velocity (%) as a line on the
 * right axis with the −threshold level, and vertical mark-lines at the entry and exit.
 * Deterministic and self-contained.
 */
export function buildVelocityChartOption(): EChartsCoreOption {
  const marks = velocitySignals().map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));
  return {
    grid: { left: 48, right: 48, top: 24, bottom: 28 },
    legend: { data: ['Price', 'Velocity (%)'], top: 0 },
    xAxis: { type: 'category', data: SYNTHETIC_PRICES.map((_, i) => String(i)), boundaryGap: false },
    yAxis: [{ type: 'value', scale: true }, { type: 'value' }],
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
        id: 'velocity',
        name: 'Velocity (%)',
        type: 'line',
        yAxisIndex: 1,
        showSymbol: true,
        itemStyle: { color: '#7c3aed' },
        data: velocities().map((v) => (v == null ? null : v * 100)),
        markLine: {
          symbol: 'none',
          data: [{ yAxis: -THRESHOLD * 100, label: { formatter: 'Threshold' } }],
          lineStyle: { type: 'dashed', color: '#64748b' },
        },
      },
    ],
  };
}
