import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TechnicalPanel } from './TechnicalPanel';
import type { WatchlistIndicator } from '../types/api';

/** A fully-populated indicator with enough history to render values. */
function withHistory(
  overrides: Partial<WatchlistIndicator> = {},
): WatchlistIndicator {
  return {
    asset_id: 1,
    ticker: 'AAA',
    trading_date: '2026-10-15',
    bar_count: 320,
    insufficient_history: false,
    rsi_14: 55.2,
    macd_line: 1.23,
    macd_signal: 1.1,
    macd_hist: 0.13,
    ema_20: 101.5,
    bb_pctb: 0.6,
    bb_width: 0.08,
    hvol_20: 0.25,
    vol_ratio_50: 1.4,
    obv_change_20d: 1_200_000,
    rev_macd_hist_rollover: true,
    rev_rsi_rollover: false,
    rev_return_decel: false,
    rev_obv_price_divergence: false,
    ...overrides,
  };
}

describe('TechnicalPanel', () => {
  it('renders indicator values, active reversal chips, and the as-of date', () => {
    render(<TechnicalPanel indicator={withHistory()} minBars={250} />);

    expect(screen.getByText('RSI (14)')).toBeInTheDocument();
    expect(screen.getByText('55.2')).toBeInTheDocument();
    // The one active reversal flag shows as a chip; inactive ones do not.
    expect(screen.getByText('MACD histogram rollover')).toBeInTheDocument();
    expect(screen.queryByText('RSI rollover')).not.toBeInTheDocument();
    expect(screen.getByText('As of 2026-10-15')).toBeInTheDocument();
  });

  it('renders the insufficient-history state below the bar floor', () => {
    render(
      <TechnicalPanel
        indicator={withHistory({
          insufficient_history: true,
          bar_count: 40,
          rsi_14: null,
        })}
        minBars={250}
      />,
    );

    expect(
      screen.getByText(/Insufficient history for technical indicators/),
    ).toBeInTheDocument();
    expect(screen.getByText(/have 40/)).toBeInTheDocument();
    expect(screen.queryByText('RSI (14)')).not.toBeInTheDocument();
  });

  it('renders a no-record note when there is no indicator', () => {
    render(<TechnicalPanel indicator={null} minBars={250} />);

    expect(
      screen.getByText('No technical indicators on record for this asset yet.'),
    ).toBeInTheDocument();
  });
});
