import type { EChartsCoreOption } from 'echarts/core';

/** Illustrative parameters: voting window, consensus level, RSI period, Bollinger k. */
const WINDOW = 10;
const CONSENSUS = 3;
const RSI_PERIOD = 14;
const BB_K = 2;

/**
 * A fixed, deterministic synthetic close series: a choppy sideways stretch, a sharp
 * sell-off (oversold consensus) and a recovery. Purely illustrative, not market data.
 */
const SYNTHETIC_PRICES = [
  100, 100.4, 100.1, 100.5, 100.2, 100.6, 100.3, 100.7, 100.4, 100.8, 100.5, 100.9, 100.6, 101,
  100.7, 101.1, 100.8, 99.6, 98.7, 98.9, 99.5, 100.1, 100.6, 101, 101.3,
] as const;

const FIRST = Math.max(WINDOW, RSI_PERIOD + 1) - 1;

function sign(value: number, low: number, high: number): number {
  if (value < low) return 1;
  if (value > high) return -1;
  return 0;
}

/** The sum of the eight course votes at bar `i` (mirrors the backend strategy). */
function scoreAt(i: number): number {
  const window = SYNTHETIC_PRICES.slice(i - WINDOW + 1, i + 1);
  const close = window[window.length - 1];
  const mean = window.reduce((a, b) => a + b, 0) / WINDOW;
  const sigma = Math.sqrt(window.reduce((a, b) => a + (b - mean) ** 2, 0) / WINDOW);
  const sorted = [...window].sort((a, b) => a - b);
  const median = (sorted[WINDOW / 2 - 1] + sorted[WINDOW / 2]) / 2;
  const low = sorted[0];
  const high = sorted[WINDOW - 1];

  const rsiCloses = SYNTHETIC_PRICES.slice(i - RSI_PERIOD, i + 1);
  let gain = 0;
  let loss = 0;
  for (let j = 1; j < rsiCloses.length; j += 1) {
    const diff = rsiCloses[j] - rsiCloses[j - 1];
    if (diff > 0) gain += diff;
    else loss -= diff;
  }
  const rsi = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  const gradientMean = window.slice(-5).reduce((a, b) => a + b, 0) / 5;
  const rank = window.filter((c) => c < close).length / WINDOW;
  const range = close >= high * 0.999 ? -1 : close <= low * 1.001 ? 1 : 0;

  return (
    (sigma === 0 ? 0 : sign((close - mean) / sigma, -1, 1)) +
    sign((close - mean) / mean, -0.01, 0.01) +
    sign(rsi, 30, 70) +
    sign(close, mean - BB_K * sigma, mean + BB_K * sigma) +
    sign(rank, 0.1, 0.9) +
    sign((close - median) / median, -0.002, 0.002) +
    sign(close - gradientMean, 0, 0) +
    range
  );
}

/** The vote score per bar (null before enough history). */
export function consensusScores(): (number | null)[] {
  return SYNTHETIC_PRICES.map((_, i) => (i < FIRST ? null : scoreAt(i)));
}

/** Bars where the score first reaches the consensus level (an entry while flat). */
export function consensusEntries(): number[] {
  const scores = consensusScores();
  return scores.flatMap((score, i) => {
    const previous = i > 0 ? scores[i - 1] : null;
    return score !== null && score >= CONSENSUS && (previous === null || previous < CONSENSUS)
      ? [i]
      : [];
  });
}

/**
 * Build the ECharts option for the illustrative Multi-Signal Consensus chart: the synthetic
 * close on the left axis, the vote score as bars on the right axis with the consensus level
 * dashed, and a vertical mark-line where the consensus is first reached.
 * Deterministic and self-contained.
 */
export function buildConsensusChartOption(): EChartsCoreOption {
  const marks = consensusEntries().map((i) => ({
    xAxis: String(i),
    lineStyle: { color: '#059669' },
    label: { formatter: 'Entry', color: '#059669' },
  }));
  return {
    grid: { left: 48, right: 40, top: 32, bottom: 28 },
    legend: { data: ['Price', 'Vote score'], top: 0 },
    xAxis: {
      type: 'category',
      data: SYNTHETIC_PRICES.map((_, i) => String(i)),
      boundaryGap: true,
    },
    yAxis: [
      { type: 'value', scale: true },
      { type: 'value', min: -8, max: 8, interval: 4 },
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
        id: 'score',
        name: 'Vote score',
        type: 'bar',
        yAxisIndex: 1,
        itemStyle: { color: '#94a3b8' },
        data: consensusScores().map((score) =>
          score === null
            ? null
            : {
                value: score,
                itemStyle: { color: score >= CONSENSUS ? '#059669' : '#cbd5e1' },
              },
        ),
        markLine: {
          symbol: 'none',
          data: [{ yAxis: CONSENSUS, label: { formatter: 'Consensus' } }],
          lineStyle: { type: 'dashed', color: '#64748b' },
        },
      },
    ],
  };
}
