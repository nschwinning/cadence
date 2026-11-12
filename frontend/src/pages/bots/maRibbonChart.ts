import type { EChartsCoreOption } from 'echarts/core';

/** SMA periods used by the illustrative chart (not the live defaults). */
const FAST = 3;
const MID = 6;
const SLOW = 10;

/**
 * A fixed, deterministic synthetic close series: a choppy base followed by a steady
 * rise that stacks the three averages fast > mid > slow (entry). Purely illustrative,
 * not market data.
 */
const SYNTHETIC_PRICES = [
  104, 102, 103, 101, 102, 100, 101, 100, 101, 100, 101, 102, 103.5, 105, 106.5, 108,
  109, 110.5, 111, 112,
] as const;

/** Per-bar simple moving average of `period` closes (null until enough history). */
export function smaSeries(period: number): (number | null)[] {
  return SYNTHETIC_PRICES.map((_, i) => {
    if (i + 1 < period) return null;
    const window = SYNTHETIC_PRICES.slice(i + 1 - period, i + 1);
    return window.reduce((a, b) => a + b, 0) / period;
  });
}

/** Index of the first bar where the ribbon stacks upward (the illustrated entry). */
export function ribbonEntryIndex(): number | null {
  const fast = smaSeries(FAST);
  const mid = smaSeries(MID);
  const slow = smaSeries(SLOW);
  for (let i = 0; i < SYNTHETIC_PRICES.length; i += 1) {
    const f = fast[i];
    const m = mid[i];
    const s = slow[i];
    if (f != null && m != null && s != null && f > m && m > s) return i;
  }
  return null;
}

/**
 * Build the ECharts option for the illustrative MA Ribbon chart: the synthetic close,
 * the fast, mid and slow averages, and a vertical mark-line where the ribbon first
 * stacks upward. Deterministic and self-contained.
 */
export function buildMaRibbonChartOption(): EChartsCoreOption {
  const entry = ribbonEntryIndex();
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
  const average = (id: string, name: string, period: number, color: string) => ({
    id,
    name,
    type: 'line',
    showSymbol: false,
    lineStyle: { width: 1 },
    itemStyle: { color },
    data: smaSeries(period),
  });
  return {
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    legend: { data: ['Price', 'Fast SMA', 'Mid SMA', 'Slow SMA'], top: 0 },
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
      average('fast', 'Fast SMA', FAST, '#059669'),
      average('mid', 'Mid SMA', MID, '#d97706'),
      average('slow', 'Slow SMA', SLOW, '#dc2626'),
    ],
  };
}
