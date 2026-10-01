import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { TechnicalIndicatorsPage } from './TechnicalIndicatorsPage';
import { apiClient } from '../../api/client';
import type { TechnicalIndicatorConfig } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const config: TechnicalIndicatorConfig = {
  indicators: [
    { key: 'sma_50', label: '50-day SMA', params: [{ name: 'period', value: 50 }] },
    {
      key: 'macd',
      label: 'MACD',
      params: [
        { name: 'fast', value: 12 },
        { name: 'slow', value: 26 },
        { name: 'signal', value: 9 },
      ],
    },
  ],
  trend_gate: {
    description: 'Deterministic uptrend gate.',
    regime: [
      { description: 'Close above SMA200', threshold: null },
      { description: 'SMA200 slope at least min', threshold: 0 },
    ],
    momentum: [{ description: 'RSI above threshold', threshold: 50 }],
    obv_bonus: 'Rising OBV is a soft bonus.',
    missing_indicator_rule: 'A missing required indicator fails the gate.',
  },
  reversal_flags: {
    flags: [
      {
        key: 'rsi_rollover',
        label: 'RSI rollover',
        description: 'RSI turns down from an overbought reading.',
      },
    ],
    rsi_overbought: 70,
    slope_flatten_eps: 0.005,
  },
};

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('TechnicalIndicatorsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the grouped configuration sections from the fetched config', async () => {
    mockedGet.mockResolvedValue({ data: config });
    renderWithClient(<TechnicalIndicatorsPage />);

    expect(await screen.findByText('Indicator set')).toBeInTheDocument();
    expect(screen.getByText('50-day SMA')).toBeInTheDocument();
    expect(screen.getByText('fast 12, slow 26, signal 9')).toBeInTheDocument();

    expect(screen.getByText('Trend gate')).toBeInTheDocument();
    expect(screen.getByText('Close above SMA200')).toBeInTheDocument();
    expect(screen.getByText('Rising OBV is a soft bonus.')).toBeInTheDocument();

    expect(screen.getByText('Reversal flags')).toBeInTheDocument();
    expect(screen.getByText('RSI rollover')).toBeInTheDocument();
    expect(screen.getByText('RSI overbought')).toBeInTheDocument();
    expect(screen.getByText('0.005')).toBeInTheDocument();
  });

  it('shows a loading state while the config is pending', () => {
    mockedGet.mockReturnValue(new Promise(() => {}));
    renderWithClient(<TechnicalIndicatorsPage />);

    expect(screen.getByRole('status')).toHaveTextContent(/loading/i);
  });

  it('shows an error state when the config fails to load', async () => {
    mockedGet.mockRejectedValue(new Error('boom'));
    renderWithClient(<TechnicalIndicatorsPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not load/i,
    );
  });
});
