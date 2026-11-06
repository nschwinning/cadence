import type { EChartsCoreOption } from 'echarts/core';
import { buildCrossoverChartOption } from './crossoverChart';
import { buildRsiChartOption } from './rsiChart';

/**
 * A strategy's illustrative (synthetic, client-side) chart: how to build its
 * ECharts option plus the aria-label describing it. Presentation-only — it is not
 * catalog data, so it lives on the frontend.
 */
export interface StrategyChartDescriptor {
  buildOption: () => EChartsCoreOption;
  ariaLabel: string;
}

/**
 * Strategy key → its illustrative chart descriptor. Only strategies that have a
 * synthetic illustration appear here; a strategy absent from this registry simply
 * renders its explanation without a chart.
 */
const STRATEGY_CHARTS: Record<string, StrategyChartDescriptor> = {
  ma_crossover: {
    buildOption: buildCrossoverChartOption,
    ariaLabel:
      'Illustrative moving-average crossover with entry and exit markers',
  },
  rsi_mean_reversion: {
    buildOption: buildRsiChartOption,
    ariaLabel:
      'Illustrative RSI mean-reversion with oversold entry and reversion exit markers',
  },
};

/** Look up a strategy's illustrative chart descriptor, or `undefined` if it has none. */
export function getStrategyChart(
  key: string,
): StrategyChartDescriptor | undefined {
  return STRATEGY_CHARTS[key];
}
