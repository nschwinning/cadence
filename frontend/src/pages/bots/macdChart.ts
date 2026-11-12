import type { EChartsCoreOption } from 'echarts/core';

/** EMA periods used by the illustrative chart (not the live defaults). */
const FAST = 3;
const SLOW = 6;
const SIGNAL = 3;

/**
 * A fixed, deterministic synthetic close series: a rise, a pull-back that drops the
 * MACD under its signal line, then a renewed rise that crosses it back up while the
 * MACD is above zero (entry). Purely illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 110, 108, 107, 107,
  109, 112, 115, 118, 120, 121,
] as const;

/** One MACD / signal pair, or null before the seed bar. */
export interface MacdPoint {
  macd: number;
  signal: number;
}

/** Replay the course MACD (seeded from simple means) — mirrors the backend helper. */
export function macdPoints(): (MacdPoint | null)[] {
  const out: (MacdPoint | null)[] = SYNTHETIC_PRICES.map(() => null);
  const seed = SYNTHETIC_PRICES.slice(0, SLOW);
  let slow = seed.reduce((a, b) => a + b, 0) / SLOW;
  let fast = seed.slice(-FAST).reduce((a, b) => a + b, 0) / FAST;
  let macd = fast - slow;
  let signal = macd;
  out[SLOW - 1] = { macd, signal };
  const a = (p: number) => 2 / (p + 1);
  for (let i = SLOW; i < SYNTHETIC_PRICES.length; i += 1) {
    const price = SYNTHETIC_PRICES[i];
    fast = price * a(FAST) + fast * (1 - a(FAST));
    slow = price * a(SLOW) + slow * (1 - a(SLOW));
    macd = fast - slow;
    signal = macd * a(SIGNAL) + signal * (1 - a(SIGNAL));
    out[i] = { macd, signal };
  }
  return out;
}

/** Index of the first bullish cross above zero (the illustrated entry), if any. */
export function macdEntryIndex(): number | null {
  const points = macdPoints();
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const cur = points[i];
    if (prev && cur && prev.macd <= prev.signal && cur.macd > cur.signal && cur.macd > 0) {
      return i;
    }
  }
  return null;
}

/**
 * Build the ECharts option for the illustrative MACD Momentum chart: the synthetic
 * close line on the left axis, MACD and its signal line on the right axis, and a
 * vertical mark-line at the entry. Deterministic and self-contained.
 */
export function buildMacdChartOption(): EChartsCoreOption {
  const x = SYNTHETIC_PRICES.map((_, i) => String(i));
  const points = macdPoints();
  const entry = macdEntryIndex();
  const marks =
    entry == null
      ? []
      : [
          {
            xAxis: String(entry),
            lineStyle: { color: '#059669' },
            label: { formatter: 'Entry', color: '#059669' },
          },
        ];
  return {
    grid: { left: 48, right: 48, top: 24, bottom: 28 },
    legend: { data: ['Price', 'MACD', 'Signal'], top: 0 },
    xAxis: { type: 'category', data: x, boundaryGap: false },
    yAxis: [{ type: 'value', scale: true }, { type: 'value', scale: true }],
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
        id: 'macd',
        name: 'MACD',
        type: 'line',
        yAxisIndex: 1,
        showSymbol: false,
        itemStyle: { color: '#7c3aed' },
        data: points.map((p) => (p ? p.macd : null)),
      },
      {
        id: 'signal',
        name: 'Signal',
        type: 'line',
        yAxisIndex: 1,
        showSymbol: false,
        lineStyle: { type: 'dashed' },
        itemStyle: { color: '#64748b' },
        data: points.map((p) => (p ? p.signal : null)),
      },
    ],
  };
}
