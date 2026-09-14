import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { PortfoliosPage } from './PortfoliosPage';
import { apiClient } from '../../api/client';
import type { Portfolio, PortfolioListResponse } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const portfolio: Portfolio = {
  id: 'p1',
  name: 'Momentum Growth',
  description: null,
  stocks: ['AAPL', 'MSFT'],
  max_allocation_pct: 0.25,
  source: 'ai_managed',
  risk_profile: 'balanced',
  source_run_id: null,
  created_at: '2026-09-10T00:00:00Z',
};

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PortfoliosPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the build card and a stored-portfolio row linking to detail', async () => {
    const body: PortfolioListResponse = { items: [portfolio], total: 1 };
    mockedGet.mockResolvedValue({ data: body });

    renderWithClient(<PortfoliosPage />);

    expect(screen.getByText('Build an AI portfolio')).toBeInTheDocument();

    const link = await screen.findByRole('link', { name: 'Momentum Growth' });
    expect(link).toHaveAttribute('href', '/portfolios/p1');
    expect(screen.getByText('25%')).toBeInTheDocument();
  });

  it('shows an empty state when there are no portfolios', async () => {
    mockedGet.mockResolvedValue({ data: { items: [], total: 0 } });

    renderWithClient(<PortfoliosPage />);

    expect(
      await screen.findByText(/No portfolios yet/i),
    ).toBeInTheDocument();
  });
});
