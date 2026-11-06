import type { EChartsCoreOption } from 'echarts/core';

/** Entry / exit channel lookbacks used by the illustrative chart (not the live defaults). */
const ENTRY_PERIOD = 5;
const EXIT_PERIOD = 3;

/**
 * A fixed, deterministic synthetic close series shaped to coil inside a channel,
 * break out above the entry-channel high (entry), run, then break down through the
 * exit-channel low (exit) — purely illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  100, 101, 99, 100, 102, 101, 100, 103, 108, 110, 112, 111, 113, 110, 107,
  104, 101, 100, 99, 98,
] as const;

/** The highest value over the `period` entries ending just before `end` (exclusive). */
function highestHigh(
  values: readonly number[],
  end: number,
  period: number,
): number | null {
  const start = end - period;
  if (start < 0) return null;
  return Math.max(...values.slice(start, end));
}

/** The lowest value over the `period` entries ending just before `end` (exclusive). */
function lowestLow(
  values: readonly number[],
  end: number,
  period: number,
): number | null {
  const start = end - period;
  if (start < 0) return null;
  return Math.min(...values.slice(start, end));
}

/** An entry/exit signal with the x-index it occurs at. */
export interface DonchianSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/**
 * Detect the illustrative long-only Donchian (Turtle) signals from the synthetic
 * series: an **entry** on the first bar whose close breaks above the prior
 * `ENTRY_PERIOD`-bar high while flat, an **exit** on the first bar whose close
 * breaks below the prior `EXIT_PERIOD`-bar low while long. Deterministic for the
 * fixed synthetic series; mirrors the backend Turtle strategy so the illustration
 * matches it.
 */
export function donchianSignals(): DonchianSignal[] {
  const signals: DonchianSignal[] = [];
  let holding = false;
  for (let i = 0; i < SYNTHETIC_PRICES.length; i += 1) {
    const close = SYNTHETIC_PRICES[i];
    if (!holding) {
      const upper = highestHigh(SYNTHETIC_PRICES, i, ENTRY_PERIOD);
      if (upper != null && close > upper) {
        signals.push({ index: i, kind: 'entry' });
        holding = true;
      }
    } else {
      const lower = lowestLow(SYNTHETIC_PRICES, i, EXIT_PERIOD);
      if (lower != null && close < lower) {
        signals.push({ index: i, kind: 'exit' });
        holding = false;
      }
    }
  }
  return signals;
}

/**
 * Build the ECharts option for the illustrative Donchian Range Breakout chart: the
 * synthetic close line with the upper (entry) and lower (exit) channel bands drawn
 * as step lines, plus vertical mark-lines at the entry (green, upward breakout) and
 * exit (red, downward breakdown) points. Fully deterministic and self-contained —
 * it takes no live data.
 */
export function buildDonchianChartOption(): EChartsCoreOption {
  const x = SYNTHETIC_PRICES.map((_, i) => String(i));
  const upper = SYNTHETIC_PRICES.map((_, i) =>
    highestHigh(SYNTHETIC_PRICES, i, ENTRY_PERIOD),
  );
  const lower = SYNTHETIC_PRICES.map((_, i) =>
    lowestLow(SYNTHETIC_PRICES, i, EXIT_PERIOD),
  );
  const signals = donchianSignals();

  const verticalMarks = signals.map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));

  return {
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    legend: { data: ['Price', 'Entry channel', 'Exit channel'], top: 0 },
    xAxis: { type: 'category', data: x, boundaryGap: false },
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
        markLine: { symbol: 'none', data: verticalMarks },
      },
      {
        id: 'entry-channel',
        name: 'Entry channel',
        type: 'line',
        step: 'end',
        showSymbol: false,
        lineStyle: { width: 1, type: 'dashed' },
        itemStyle: { color: '#059669' },
        data: upper,
      },
      {
        id: 'exit-channel',
        name: 'Exit channel',
        type: 'line',
        step: 'end',
        showSymbol: false,
        lineStyle: { width: 1, type: 'dashed' },
        itemStyle: { color: '#dc2626' },
        data: lower,
      },
    ],
  };
}
