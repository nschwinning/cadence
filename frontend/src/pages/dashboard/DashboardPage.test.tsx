import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { DashboardPage } from './DashboardPage';
import { apiClient } from '../../api/client';
import type { DashboardMetrics, HealthResponse } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
  getHealth: vi.fn(() =>
    Promise.resolve({ status: 'ok', database: 'connected' }),
  ),
}));

const mockedGet = vi.mocked(apiClient.get);

const metrics: DashboardMetrics = {
  assets: {
    total: 120,
    eligible: 90,
    ineligible: 30,
    by_category: [
      { key: 'stock', count: 100 },
      { key: 'etf', count: 20 },
    ],
    by_sector: [{ key: 'technology', count: 40 }],
  },
  portfolio_count: 5,
  paper_trading: { active_sessions: 2, recent_trades: 7 },
};

const health: HealthResponse = { status: 'ok', database: 'connected' };

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGet.mockImplementation((url: string) => {
      if (url.includes('/dashboard/metrics')) return Promise.resolve({ data: metrics });
      if (url.includes('/health')) return Promise.resolve({ data: health });
      return Promise.resolve({ data: {} });
    });
  });

  it('renders the universe, activity, and breakdown tiles from the metrics endpoint', async () => {
    renderWithClient(<DashboardPage />);

    expect(await screen.findByText('Universe size')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('Eligible assets')).toBeInTheDocument();
    expect(screen.getByText('90')).toBeInTheDocument();
    expect(screen.getByText('Portfolios')).toBeInTheDocument();
    expect(screen.getByText('Active sessions')).toBeInTheDocument();
    expect(screen.getByText('By category')).toBeInTheDocument();
    expect(screen.getByText('By sector')).toBeInTheDocument();
  });
});
