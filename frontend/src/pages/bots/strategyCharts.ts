import type { EChartsCoreOption } from 'echarts/core';
import { buildAdxChartOption } from './adxChart';
import { buildAtrBandChartOption } from './atrBandChart';
import { buildBayesianChartOption } from './bayesianChart';
import { buildConsensusChartOption } from './consensusChart';
import { buildCrossoverChartOption } from './crossoverChart';
import { buildMacdChartOption } from './macdChart';
import { buildMaRibbonChartOption } from './maRibbonChart';
import { buildDonchianChartOption } from './donchianChart';
import { buildHeikinAshiChartOption } from './heikinAshiChart';
import { buildHmaChartOption } from './hmaChart';
import { buildRollingReversionChartOption } from './rollingReversionChart';
import { buildRsiChartOption } from './rsiChart';
import { buildTrendConfirmationChartOption } from './trendConfirmationChart';
import { buildVamaChartOption } from './vamaChart';
import { buildVelocityChartOption } from './velocityChart';
import { buildVolatilityRegimeChartOption } from './volatilityRegimeChart';
import { buildVolumeBreakoutChartOption } from './volumeBreakoutChart';

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
  donchian_breakout: {
    buildOption: buildDonchianChartOption,
    ariaLabel:
      'Illustrative Donchian range breakout with an upward-breakout entry and a downward-breakdown exit marker',
  },
  rolling_average_reversion: {
    buildOption: buildRollingReversionChartOption,
    ariaLabel:
      'Illustrative rolling-average reversion with a dip-below-the-band entry and a revert-to-the-average exit marker',
  },
  atr_band_trend: {
    buildOption: buildAtrBandChartOption,
    ariaLabel:
      'Illustrative ATR-band trend (Keltner) with an upper-band breakout entry and a below-the-average exit marker',
  },
  adx_trend: {
    buildOption: buildAdxChartOption,
    ariaLabel:
      'Illustrative ADX trend strength with an entry as the ADX rises above its threshold and an exit as it falls back below',
  },
  macd_momentum: {
    buildOption: buildMacdChartOption,
    ariaLabel:
      'Illustrative MACD momentum with an entry where the MACD crosses above its signal line above zero',
  },
  heikin_ashi_trend: {
    buildOption: buildHeikinAshiChartOption,
    ariaLabel:
      'Illustrative Heikin-Ashi candles with an entry on the first green candle and an exit on the first red one',
  },
  hma_trend: {
    buildOption: buildHmaChartOption,
    ariaLabel:
      'Illustrative HMA trend with an entry as the rising fast Hull average clears the slow one and an exit on the falling cross below',
  },
  ma_ribbon: {
    buildOption: buildMaRibbonChartOption,
    ariaLabel:
      'Illustrative MA ribbon with an entry where the fast, mid and slow averages stack upward',
  },
  vama: {
    buildOption: buildVamaChartOption,
    ariaLabel:
      'Illustrative VAMA with fixed and adaptive smoothing, an entry above the average and an exit back below it',
  },
  price_velocity_reversal: {
    buildOption: buildVelocityChartOption,
    ariaLabel:
      'Illustrative price velocity reversal with an entry on a slowing sell-off and an exit on the first up-bar',
  },
  trend_confirmation: {
    buildOption: buildTrendConfirmationChartOption,
    ariaLabel:
      'Illustrative trend confirmation with an entry where every trend check agrees and an exit where one breaks',
  },
  volume_breakout: {
    buildOption: buildVolumeBreakoutChartOption,
    ariaLabel:
      'Illustrative volume breakout with an entry on a high-volume break above the prior high and an exit on a high-volume break below the prior low',
  },
  volatility_regime: {
    buildOption: buildVolatilityRegimeChartOption,
    ariaLabel:
      'Illustrative volatility regime switcher with a trend trade above the range midpoint while calm and a dip-buy back to the moving average while volatile',
  },
  signal_consensus: {
    buildOption: buildConsensusChartOption,
    ariaLabel:
      'Illustrative multi-signal consensus with the vote score under the price and an entry where the oversold votes reach the consensus level',
  },
  bayesian_trend: {
    buildOption: buildBayesianChartOption,
    ariaLabel:
      'Illustrative Bayesian trend predictor with up, flat and down regime probabilities under the price, an entry on a confident up-regime and an exit on a confident down-regime',
  },
};

/** Look up a strategy's illustrative chart descriptor, or `undefined` if it has none. */
export function getStrategyChart(
  key: string,
): StrategyChartDescriptor | undefined {
  return STRATEGY_CHARTS[key];
}
