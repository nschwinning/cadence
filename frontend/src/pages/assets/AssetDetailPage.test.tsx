import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import { AssetDetailPage } from './AssetDetailPage';
import { apiClient } from '../../api/client';
import type { AssetDetail } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const detail: AssetDetail = {
  ticker: 'AAPL',
  name: 'Apple Inc.',
  category: 'stock',
  sector: 'technology',
  exchange: 'NASDAQ',
  currency: 'USD',
  current_price: 190,
  previous_close: 180,
  short_description: 'Consumer electronics.',
  country: 'United States',
  city: 'Cupertino',
  employees: 160000,
  website: 'https://apple.com',
  volume: 50_000_000,
  avg_volume: 60_000_000,
  price_history: [
    { date: '2026-09-01', close: 180 },
    { date: '2026-09-02', close: 185 },
    { date: '2026-09-03', close: 190 },
  ],
  snapshot_date: '2026-09-03',
};

function renderAt(path: string, ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/assets/:ticker" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AssetDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the asset name, price, and company facts', async () => {
    mockedGet.mockResolvedValue({ data: detail });

    renderAt('/assets/AAPL', <AssetDetailPage />);

    expect(
      await screen.findByRole('heading', { name: 'Apple Inc.' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Consumer electronics.')).toBeInTheDocument();
    expect(screen.getByText('Cupertino')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'https://apple.com' }),
    ).toBeInTheDocument();
  });

  it('shows a not-found state on a 404', async () => {
    const axios = await import('axios');
    vi.spyOn(axios.default, 'isAxiosError').mockReturnValue(true);
    mockedGet.mockRejectedValue({
      isAxiosError: true,
      response: { status: 404 },
    });

    renderAt('/assets/NOPE', <AssetDetailPage />);

    expect(
      await screen.findByRole('heading', { name: 'Asset not found' }),
    ).toBeInTheDocument();
  });
});
