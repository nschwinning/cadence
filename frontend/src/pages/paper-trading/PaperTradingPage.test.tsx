import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { PaperTradingPage } from './PaperTradingPage';
import { apiClient } from '../../api/client';
import type {
  PaperTradingSession,
  PaperTradingSessionListResponse,
} from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const session: PaperTradingSession = {
  id: 's1',
  portfolio_id: 'p1',
  strategy_key: 'ai-momentum',
  status: 'active',
  allocated_capital: 100000,
  max_allocation_pct: 0.25,
  created_at: '2026-09-10T00:00:00Z',
  updated_at: '2026-09-12T00:00:00Z',
  last_run_at: '2026-09-12T09:30:00Z',
  total_trades: 12,
  total_pnl: 1500,
  session_metadata: null,
  schedule_mode: 'DAILY_REBALANCING',
};

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

describe('PaperTradingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a session row linking to its detail page', async () => {
    const body: PaperTradingSessionListResponse = {
      items: [session],
      total: 1,
    };
    mockedGet.mockResolvedValue({ data: body });

    renderWithClient(<PaperTradingPage />);

    const link = await screen.findByRole('link', { name: 'ai-momentum' });
    expect(link).toHaveAttribute('href', '/paper-trading/s1');
    expect(screen.getByText('active')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('shows an empty state with no sessions', async () => {
    mockedGet.mockResolvedValue({ data: { items: [], total: 0 } });

    renderWithClient(<PaperTradingPage />);

    expect(
      await screen.findByText(/No paper-trading sessions yet/i),
    ).toBeInTheDocument();
  });
});
