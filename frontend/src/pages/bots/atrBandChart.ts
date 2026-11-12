import type { EChartsCoreOption } from 'echarts/core';

/** Window and ATR multiplier used by the illustrative chart (not the live defaults). */
const WINDOW = 5;
const ATR_MULT = 1;

/**
 * A fixed, deterministic synthetic close series shaped to drift sideways, break out
 * above the upper Keltner band (entry), trend higher, then fall back below the moving
 * average (exit) — purely illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  100, 101, 100, 101, 100, 101, 100, 104, 107, 109, 111, 112, 113, 112, 110,
  107, 104, 102, 101, 100,
] as const;

/** Mean of the `WINDOW` closes ending at `end` (inclusive), or null before a full window. */
export function windowMean(values: readonly number[], end: number): number | null {
  const start = end - WINDOW + 1;
  if (start < 0) return null;
  const window = values.slice(start, end + 1);
  return window.reduce((sum, v) => sum + v, 0) / window.length;
}

/** The course ATR proxy over the window ending at `end`: mean absolute close change. */
export function windowAtr(values: readonly number[], end: number): number | null {
  const start = end - WINDOW + 1;
  if (start < 0) return null;
  const window = values.slice(start, end + 1);
  let total = 0;
  for (let i = 1; i < window.length; i += 1) total += Math.abs(window[i] - window[i - 1]);
  return total / (window.length - 1);
}

/** An entry/exit signal with the x-index it occurs at. */
export interface AtrBandSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/**
 * Detect the illustrative long-only Keltner signals from the synthetic series: an
 * **entry** on the first close above the upper band (mean + ATR_MULT × ATR) while
 * flat, an **exit** on the first close below the mean while long. Mirrors the backend
 * ATR-Band Trend strategy's Keltner version.
 */
export function atrBandSignals(): AtrBandSignal[] {
  const signals: AtrBandSignal[] = [];
  let holding = false;
  for (let i = 0; i < SYNTHETIC_PRICES.length; i += 1) {
    const mean = windowMean(SYNTHETIC_PRICES, i);
    const atr = windowAtr(SYNTHETIC_PRICES, i);
    if (mean == null || atr == null) continue;
    const close = SYNTHETIC_PRICES[i];
    if (!holding && close > mean + ATR_MULT * atr) {
      signals.push({ index: i, kind: 'entry' });
      holding = true;
    } else if (holding && close < mean) {
      signals.push({ index: i, kind: 'exit' });
      holding = false;
    }
  }
  return signals;
}

/**
 * Build the ECharts option for the illustrative ATR-Band Trend (Keltner) chart: the
 * synthetic close line, the moving average, and the upper / lower ATR bands, plus
 * vertical mark-lines at the entry (green, upper-band breakout) and exit (red, close
 * back below the average). Fully deterministic and self-contained.
 */
export function buildAtrBandChartOption(): EChartsCoreOption {
  const x = SYNTHETIC_PRICES.map((_, i) => String(i));
  const mean = SYNTHETIC_PRICES.map((_, i) => windowMean(SYNTHETIC_PRICES, i));
  const atr = SYNTHETIC_PRICES.map((_, i) => windowAtr(SYNTHETIC_PRICES, i));
  const upper = mean.map((m, i) => (m == null || atr[i] == null ? null : m + ATR_MULT * atr[i]!));
  const lower = mean.map((m, i) => (m == null || atr[i] == null ? null : m - ATR_MULT * atr[i]!));

  const verticalMarks = atrBandSignals().map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));
  const band = (id: string, name: string, data: (number | null)[], color: string) => ({
    id,
    name,
    type: 'line',
    showSymbol: false,
    lineStyle: { width: 1, type: 'dashed' },
    itemStyle: { color },
    data,
  });

  return {
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    legend: { data: ['Price', 'Moving average', 'Upper band', 'Lower band'], top: 0 },
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
        id: 'mean',
        name: 'Moving average',
        type: 'line',
        showSymbol: false,
        lineStyle: { width: 1 },
        itemStyle: { color: '#64748b' },
        data: mean,
      },
      band('upper', 'Upper band', upper, '#059669'),
      band('lower', 'Lower band', lower, '#dc2626'),
    ],
  };
}
