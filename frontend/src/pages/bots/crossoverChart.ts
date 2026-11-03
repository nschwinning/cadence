import type { EChartsCoreOption } from 'echarts/core';

/** Fast / slow SMA periods used by the illustrative chart (not the live defaults). */
const FAST_PERIOD = 3;
const SLOW_PERIOD = 6;

/**
 * A fixed, deterministic synthetic price series shaped to produce one clear
 * up-cross (entry) followed by one down-cross (exit) — purely illustrative, not
 * market data.
 */
const SYNTHETIC_PRICES = [
  106, 105, 104, 102, 100, 99, 98, 98, 99, 101, 104, 108, 111, 113, 114, 113,
  110, 106, 102, 99,
] as const;

/** Simple trailing moving average; the first `period-1` points are null (warm-up). */
function sma(values: readonly number[], period: number): (number | null)[] {
  return values.map((_, i) => {
    if (i < period - 1) return null;
    let sum = 0;
    for (let j = i - period + 1; j <= i; j += 1) sum += values[j];
    return sum / period;
  });
}

/** An entry/exit signal with the x-index it occurs at. */
export interface CrossoverSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/**
 * Detect crossover signals from the synthetic fast/slow SMA series: an **entry**
 * where the fast SMA crosses from at-or-below to above the slow SMA, an **exit**
 * on the reverse cross. Deterministic for the fixed synthetic series.
 */
export function crossoverSignals(): CrossoverSignal[] {
  const fast = sma(SYNTHETIC_PRICES, FAST_PERIOD);
  const slow = sma(SYNTHETIC_PRICES, SLOW_PERIOD);
  const signals: CrossoverSignal[] = [];
  for (let i = 1; i < SYNTHETIC_PRICES.length; i += 1) {
    const f0 = fast[i - 1];
    const s0 = slow[i - 1];
    const f1 = fast[i];
    const s1 = slow[i];
    if (f0 == null || s0 == null || f1 == null || s1 == null) continue;
    if (f0 <= s0 && f1 > s1) signals.push({ index: i, kind: 'entry' });
    else if (f0 >= s0 && f1 < s1) signals.push({ index: i, kind: 'exit' });
  }
  return signals;
}

/**
 * Build the ECharts option for the illustrative MA-crossover chart: a fast and a
 * slow SMA line over a synthetic price series, with vertical mark-lines at the
 * entry (green up-cross) and exit (red down-cross) points. Fully deterministic and
 * self-contained — it takes no live data.
 */
export function buildCrossoverChartOption(): EChartsCoreOption {
  const fast = sma(SYNTHETIC_PRICES, FAST_PERIOD);
  const slow = sma(SYNTHETIC_PRICES, SLOW_PERIOD);
  const x = SYNTHETIC_PRICES.map((_, i) => String(i));
  const signals = crossoverSignals();

  const markLineData = signals.map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));

  return {
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    legend: { data: ['Fast SMA', 'Slow SMA'], top: 0 },
    xAxis: { type: 'category', data: x, boundaryGap: false },
    yAxis: { type: 'value', scale: true },
    series: [
      {
        id: 'fast',
        name: 'Fast SMA',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: '#0ea5e9' },
        data: fast,
        markLine: {
          symbol: 'none',
          data: markLineData,
        },
      },
      {
        id: 'slow',
        name: 'Slow SMA',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 2 },
        itemStyle: { color: '#64748b' },
        data: slow,
      },
    ],
  };
}
