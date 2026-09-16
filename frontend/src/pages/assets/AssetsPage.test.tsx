import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { AssetsPage } from './AssetsPage';
import { apiClient } from '../../api/client';
import type { Asset, AssetPage } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

/** Minimal IntersectionObserver stub so the infinite-scroll effect is inert. */
class NoopIntersectionObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

function page(items: Asset[], total = items.length): { data: AssetPage } {
  return { data: { items, total } };
}

const apple: Asset = {
  id: 1,
  ticker: 'AAPL',
  name: 'Apple Inc.',
  alpaca_symbol: 'AAPL',
  category: 'stock',
  sector: 'technology',
  exchange: 'NASDAQ',
  currency: 'USD',
  market_cap_usd: 2_500_000_000_000,
  avg_daily_turnover_usd: 8_000_000_000,
  history_years: 20,
  is_eligible: true,
  criteria_results: [],
  created_at: '2026-08-01T00:00:00Z',
};

const bitcoin: Asset = {
  ...apple,
  id: 2,
  ticker: 'BTCUSD',
  name: 'Bitcoin',
  category: 'crypto',
  sector: null,
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

describe('AssetsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.stubGlobal('IntersectionObserver', NoopIntersectionObserver);
    mockedGet.mockResolvedValue(page([apple]));
  });

  it('renders an asset row linking to its detail page and a total from the envelope', async () => {
    mockedGet.mockResolvedValue(page([apple], 7));

    renderWithClient(<AssetsPage />);

    const row = (await screen.findByText('Apple Inc.')).closest('tr');
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText('Eligible')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'AAPL' })).toHaveAttribute(
      'href',
      '/assets/AAPL',
    );
    expect(screen.getByText('Showing 1 of 7')).toBeInTheDocument();
  });

  it('shows a category badge distinguishing a crypto asset from a stock', async () => {
    mockedGet.mockResolvedValue(page([apple, bitcoin]));

    renderWithClient(<AssetsPage />);

    const cryptoRow = (await screen.findByText('Bitcoin')).closest('tr');
    expect(cryptoRow).not.toBeNull();
    expect(
      within(cryptoRow as HTMLElement).getByText('Crypto'),
    ).toBeInTheDocument();

    const stockRow = screen.getByText('Apple Inc.').closest('tr');
    expect(
      within(stockRow as HTMLElement).getByText('Stock'),
    ).toBeInTheDocument();
  });

  it('offers only stock and crypto in the category filter', async () => {
    const user = userEvent.setup();

    renderWithClient(<AssetsPage />);
    await screen.findByText('Apple Inc.');

    await user.click(screen.getByRole('button', { name: /Categories/ }));

    expect(screen.getByLabelText('Filter by Stock')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter by Crypto')).toBeInTheDocument();
    expect(screen.queryByLabelText('Filter by ETF')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Filter by Fund')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Filter by Other')).not.toBeInTheDocument();
  });

  it('labels failed criteria from each asset\'s own thresholds (crypto vs stock)', async () => {
    const ineligibleStock: Asset = {
      ...apple,
      id: 10,
      ticker: 'TINY',
      name: 'Tiny Stock',
      is_eligible: false,
      criteria_results: [
        { name: 'market_cap', passed: false, value: 5, threshold: 1_000_000_000 },
        { name: 'history', passed: false, value: 2, threshold: 5 },
      ],
    };
    const ineligibleCrypto: Asset = {
      ...bitcoin,
      id: 11,
      ticker: 'NEWCOIN',
      name: 'New Coin',
      is_eligible: false,
      criteria_results: [
        { name: 'market_cap', passed: false, value: 5, threshold: 2_000_000_000 },
        { name: 'avg_daily_turnover', passed: false, value: 5, threshold: 10_000_000 },
        { name: 'history', passed: false, value: 0.5, threshold: 1 },
      ],
    };
    mockedGet.mockResolvedValue(page([ineligibleStock, ineligibleCrypto]));

    renderWithClient(<AssetsPage />);

    const stockRow = (await screen.findByText('Tiny Stock')).closest('tr');
    expect(
      within(stockRow as HTMLElement).getByText('Not eligible'),
    ).toHaveAttribute('title', 'Failed: Market cap > $1.0B, History ≥ 5 years');

    const cryptoRow = screen.getByText('New Coin').closest('tr');
    expect(
      within(cryptoRow as HTMLElement).getByText('Not eligible'),
    ).toHaveAttribute(
      'title',
      'Failed: Market cap > $2.0B, Avg daily turnover ≥ $10.0M, History ≥ 1 year',
    );
  });

  it('surfaces a specific message when adding a duplicate ticker (409)', async () => {
    const user = userEvent.setup();
    mockedPost.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409 },
    });
    // Make axios.isAxiosError recognize our shape.
    const axios = await import('axios');
    vi.spyOn(axios.default, 'isAxiosError').mockReturnValue(true);

    renderWithClient(<AssetsPage />);
    await screen.findByText('Apple Inc.');

    await user.type(screen.getByLabelText('Ticker symbol'), 'AAPL');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(
      await screen.findByText('That asset already exists in your universe.'),
    ).toBeInTheDocument();
  });
});
