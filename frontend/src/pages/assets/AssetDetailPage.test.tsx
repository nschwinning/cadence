import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import { AssetDetailPage } from './AssetDetailPage';
import { apiClient } from '../../api/client';
import type {
  AssetDetail,
  AssetFundamentals,
  AssetIndicatorResponse,
  WatchlistIndicator,
} from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const baseDetail: AssetDetail = {
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
  fundamentals: null,
};

const fundamentals: AssetFundamentals = {
  source: 'sec-edgar',
  status: 'available',
  cik: '0000320193',
  document: {
    figures: { revenue: { value: 1_000_000_000, period_end: '2025-12-31' } },
    company_details: {},
  },
  fetched_at: '2026-10-15T00:00:00Z',
};

function indicator(
  overrides: Partial<WatchlistIndicator> = {},
): WatchlistIndicator {
  return {
    asset_id: 1,
    ticker: 'AAPL',
    trading_date: '2026-09-03',
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
    rev_macd_hist_rollover: false,
    rev_rsi_rollover: false,
    rev_return_decel: false,
    rev_obv_price_divergence: false,
    ...overrides,
  };
}

/**
 * Route the two GET calls the detail page makes: the detail read and the
 * per-asset technical read.
 */
function mockRoutes(
  detail: AssetDetail,
  indicatorResponse: AssetIndicatorResponse,
) {
  mockedGet.mockImplementation((url: string) => {
    if (url.includes('/technical-indicators/assets/')) {
      return Promise.resolve({ data: indicatorResponse });
    }
    return Promise.resolve({ data: detail });
  });
}

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
    mockRoutes(baseDetail, { min_bars: 250, indicator: indicator() });

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

  it('shows fundamentals when present', async () => {
    mockRoutes(
      { ...baseDetail, fundamentals },
      { min_bars: 250, indicator: indicator() },
    );

    renderAt('/assets/AAPL', <AssetDetailPage />);

    expect(
      await screen.findByRole('heading', { name: 'Fundamentals' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Revenue')).toBeInTheDocument();
    expect(screen.getByText('$1.0B')).toBeInTheDocument();
  });

  it('shows an unavailable note when fundamentals are absent', async () => {
    mockRoutes(baseDetail, { min_bars: 250, indicator: indicator() });

    renderAt('/assets/AAPL', <AssetDetailPage />);

    expect(
      await screen.findByText('No fundamentals on record for this asset.'),
    ).toBeInTheDocument();
  });

  it('shows the technical profile at or above the bar floor', async () => {
    mockRoutes(baseDetail, { min_bars: 250, indicator: indicator() });

    renderAt('/assets/AAPL', <AssetDetailPage />);

    expect(await screen.findByText('RSI (14)')).toBeInTheDocument();
    expect(screen.getByText('55.2')).toBeInTheDocument();
  });

  it('shows the insufficient-history state below the bar floor', async () => {
    mockRoutes(baseDetail, {
      min_bars: 250,
      indicator: indicator({
        insufficient_history: true,
        bar_count: 40,
        rsi_14: null,
      }),
    });

    renderAt('/assets/AAPL', <AssetDetailPage />);

    expect(
      await screen.findByText(/Insufficient history for technical indicators/),
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
