import type { EChartsCoreOption } from 'echarts/core';

/** Rolling window, entry band and exit band used by the illustrative chart (not the live defaults). */
const WINDOW = 5;
const ENTRY_BAND = 0.02;
const EXIT_BAND = 0.005;

/**
 * A fixed, deterministic synthetic close series shaped to hover around its mean,
 * dip well below it (entry), then snap back to and above it (exit) — purely
 * illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  100, 100.5, 99.8, 100.2, 100, 99.5, 97, 95, 94.5, 95.5, 97, 98.5, 99.5, 100.5,
  101, 100.5, 100, 100.5,
] as const;

/** The mean of the `WINDOW` closes ending at `end` (inclusive), or null before a full window. */
export function rollingMean(values: readonly number[], end: number): number | null {
  const start = end - WINDOW + 1;
  if (start < 0) return null;
  const slice = values.slice(start, end + 1);
  return slice.reduce((sum, v) => sum + v, 0) / slice.length;
}

/** An entry/exit signal with the x-index it occurs at. */
export interface ReversionSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/**
 * Detect the illustrative long-only band-reversion signals from the synthetic series:
 * an **entry** when the close drops more than `ENTRY_BAND` below its rolling mean
 * while flat, an **exit** once it is back within `EXIT_BAND` of (or above) the mean
 * while long. Mirrors the backend strategy's SMA band / revert mode.
 */
export function reversionSignals(): ReversionSignal[] {
  const signals: ReversionSignal[] = [];
  let holding = false;
  for (let i = 0; i < SYNTHETIC_PRICES.length; i += 1) {
    const mean = rollingMean(SYNTHETIC_PRICES, i);
    if (mean == null) continue;
    const deviation = (SYNTHETIC_PRICES[i] - mean) / mean;
    if (!holding && deviation < -ENTRY_BAND) {
      signals.push({ index: i, kind: 'entry' });
      holding = true;
    } else if (holding && deviation >= -EXIT_BAND) {
      signals.push({ index: i, kind: 'exit' });
      holding = false;
    }
  }
  return signals;
}

/**
 * Build the ECharts option for the illustrative Rolling-Average Reversion chart: the
 * synthetic close line, its rolling mean, and the entry band below the mean, plus
 * vertical mark-lines at the entry (green, dip below the band) and exit (red, reverted
 * to the mean) points. Fully deterministic and self-contained — it takes no live data.
 */
export function buildRollingReversionChartOption(): EChartsCoreOption {
  const x = SYNTHETIC_PRICES.map((_, i) => String(i));
  const mean = SYNTHETIC_PRICES.map((_, i) => rollingMean(SYNTHETIC_PRICES, i));
  const band = mean.map((m) => (m == null ? null : m * (1 - ENTRY_BAND)));
  const signals = reversionSignals();

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
    legend: { data: ['Price', 'Rolling average', 'Entry band'], top: 0 },
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
        id: 'rolling-average',
        name: 'Rolling average',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 1 },
        itemStyle: { color: '#64748b' },
        data: mean,
      },
      {
        id: 'entry-band',
        name: 'Entry band',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 1, type: 'dashed' },
        itemStyle: { color: '#059669' },
        data: band,
      },
    ],
  };
}
