import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import { PortfolioDetailPage } from './PortfolioDetailPage';
import { apiClient } from '../../api/client';
import type { Portfolio } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const portfolio: Portfolio = {
  id: 'p1',
  name: 'Momentum Growth',
  description: 'AI-selected growth names.',
  stocks: ['AAPL', 'MSFT'],
  max_allocation_pct: 0.25,
  source: 'ai_managed',
  risk_profile: 'balanced',
  source_run_id: null,
  created_at: '2026-09-10T00:00:00Z',
  archived_at: null,
};

function renderAt(path: string, ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/portfolios/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PortfolioDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders overview facts and holdings linking to asset detail', async () => {
    mockedGet.mockResolvedValue({ data: portfolio });

    renderAt('/portfolios/p1', <PortfolioDetailPage />);

    expect(
      await screen.findByRole('heading', { name: 'Momentum Growth' }),
    ).toBeInTheDocument();
    expect(screen.getByText('AI-selected growth names.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AAPL' })).toHaveAttribute(
      'href',
      '/assets/AAPL',
    );
  });

  it('shows a not-found state on a 404', async () => {
    const axios = await import('axios');
    vi.spyOn(axios.default, 'isAxiosError').mockReturnValue(true);
    mockedGet.mockRejectedValue({
      isAxiosError: true,
      response: { status: 404 },
    });

    renderAt('/portfolios/nope', <PortfolioDetailPage />);

    expect(
      await screen.findByRole('heading', { name: 'Portfolio not found' }),
    ).toBeInTheDocument();
  });
});
