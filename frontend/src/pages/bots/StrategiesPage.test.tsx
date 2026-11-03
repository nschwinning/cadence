import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { StrategiesPage } from './StrategiesPage';
import { buildCrossoverChartOption, crossoverSignals } from './crossoverChart';
import { apiClient } from '../../api/client';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

function renderPage(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('crossoverChart', () => {
  it('detects one entry up-cross and one exit down-cross', () => {
    const signals = crossoverSignals();
    expect(signals.some((s) => s.kind === 'entry')).toBe(true);
    expect(signals.some((s) => s.kind === 'exit')).toBe(true);
  });

  it('builds a two-line option with entry/exit mark-lines', () => {
    const option = buildCrossoverChartOption() as {
      series: { name: string; markLine?: { data: unknown[] } }[];
    };
    expect(option.series).toHaveLength(2);
    expect(option.series.map((s) => s.name)).toEqual(['Fast SMA', 'Slow SMA']);
    const markLine = option.series[0].markLine;
    expect(markLine?.data.length).toBeGreaterThanOrEqual(2);
  });
});

describe('StrategiesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the catalog explanation and the illustrative chart', async () => {
    mockedGet.mockResolvedValue({
      data: [
        {
          key: 'ma_crossover',
          display_name: 'MA Crossover',
          explanation: 'Buys when the fast SMA crosses above the slow SMA.',
          required_history: 51,
          params_schema: {},
        },
      ],
    });

    renderPage(<StrategiesPage />);

    expect(
      await screen.findByText(
        'Buys when the fast SMA crosses above the slow SMA.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('img', {
        name: /crossover with entry and exit markers/i,
      }),
    ).toBeInTheDocument();
    // Risk-control docs are present too.
    expect(screen.getByText('Shared budget ceiling')).toBeInTheDocument();
    expect(screen.getByText('ATR position sizing')).toBeInTheDocument();
  });

  it('shows an error state when the catalog fails to load', async () => {
    mockedGet.mockRejectedValue(new Error('boom'));

    renderPage(<StrategiesPage />);

    expect(
      await screen.findByText(/Could not load the strategy catalog/i),
    ).toBeInTheDocument();
  });
});
