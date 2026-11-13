import type { EChartsCoreOption } from 'echarts/core';

/** Illustrative Spike parameters: lookback (bars incl. the current), volume window, multiplier. */
const LOOKBACK = 8;
const VOLUME_WINDOW = 5;
const MULTIPLIER = 1.5;

/**
 * A fixed, deterministic synthetic close and volume series: a quiet range, a breakout on
 * heavy volume (entry), a drift up, then a breakdown on heavy volume (exit). Purely
 * illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  100.4, 100.8, 100.2, 100.6, 100.9, 100.3, 100.7, 100.5, 100.8, 100.4, 102.2, 102.8,
  103.4, 103.9, 104.3, 104.0, 104.4, 103.9, 103.6, 103.8, 103.4, 102.1, 101.9, 102.0,
] as const;
const SYNTHETIC_VOLUMES = [
  1000, 950, 1050, 980, 1020, 990, 1010, 970, 1030, 1000, 3200, 1600,
  1300, 1200, 1100, 1000, 1050, 980, 1020, 990, 1000, 2900, 1400, 1100,
] as const;

/** The prior range (highest / lowest close of the `LOOKBACK − 1` earlier bars), null before. */
export function priorRange(): { high: number | null; low: number | null }[] {
  return SYNTHETIC_PRICES.map((_, i) => {
    if (i < LOOKBACK - 1) return { high: null, low: null };
    const prior = SYNTHETIC_PRICES.slice(i - LOOKBACK + 1, i);
    return { high: Math.max(...prior), low: Math.min(...prior) };
  });
}

/** Whether bar `i`'s volume exceeds `MULTIPLIER` × the average of the latest window. */
function isSpike(i: number): boolean {
  const window = SYNTHETIC_VOLUMES.slice(Math.max(0, i - VOLUME_WINDOW + 1), i + 1);
  const average = window.reduce((a, b) => a + b, 0) / window.length;
  return SYNTHETIC_VOLUMES[i] > average * MULTIPLIER;
}

/** An entry/exit signal with the x-index it occurs at. */
export interface VolumeSignal {
  index: number;
  kind: 'entry' | 'exit';
}

/** Entry on a volume-confirmed breakout; exit on a volume-confirmed breakdown. */
export function volumeSignals(): VolumeSignal[] {
  const ranges = priorRange();
  const signals: VolumeSignal[] = [];
  let holding = false;
  for (let i = LOOKBACK - 1; i < SYNTHETIC_PRICES.length; i += 1) {
    const { high, low } = ranges[i];
    const close = SYNTHETIC_PRICES[i];
    if (!holding && close > high! && isSpike(i)) {
      signals.push({ index: i, kind: 'entry' });
      holding = true;
    } else if (holding && close < low! && isSpike(i)) {
      signals.push({ index: i, kind: 'exit' });
      holding = false;
    }
  }
  return signals;
}

/**
 * Build the ECharts option for the illustrative Volume Breakout (Spike) chart: the
 * synthetic close with its prior high / low on the left axis, volume bars on the right
 * axis, and vertical mark-lines at the entry and exit. Deterministic and self-contained.
 */
export function buildVolumeBreakoutChartOption(): EChartsCoreOption {
  const ranges = priorRange();
  const marks = volumeSignals().map((s) => ({
    xAxis: String(s.index),
    lineStyle: { color: s.kind === 'entry' ? '#059669' : '#dc2626' },
    label: {
      formatter: s.kind === 'entry' ? 'Entry' : 'Exit',
      color: s.kind === 'entry' ? '#059669' : '#dc2626',
    },
  }));
  return {
    grid: { left: 48, right: 56, top: 24, bottom: 28 },
    legend: { data: ['Price', 'Prior high', 'Prior low', 'Volume'], top: 0 },
    xAxis: {
      type: 'category',
      data: SYNTHETIC_PRICES.map((_, i) => String(i)),
      boundaryGap: true,
    },
    yAxis: [
      { type: 'value', scale: true },
      { type: 'value', max: Math.max(...SYNTHETIC_VOLUMES) * 3, show: false },
    ],
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
        id: 'prior-high',
        name: 'Prior high',
        type: 'line',
        step: 'middle',
        showSymbol: false,
        lineStyle: { type: 'dashed', width: 1 },
        itemStyle: { color: '#059669' },
        data: ranges.map((r) => r.high),
      },
      {
        id: 'prior-low',
        name: 'Prior low',
        type: 'line',
        step: 'middle',
        showSymbol: false,
        lineStyle: { type: 'dashed', width: 1 },
        itemStyle: { color: '#dc2626' },
        data: ranges.map((r) => r.low),
      },
      {
        id: 'volume',
        name: 'Volume',
        type: 'bar',
        yAxisIndex: 1,
        itemStyle: { color: '#94a3b8' },
        data: SYNTHETIC_VOLUMES.map((v, i) => ({
          value: v,
          itemStyle: { color: isSpike(i) ? '#f59e0b' : '#cbd5e1' },
        })),
      },
    ],
  };
}
