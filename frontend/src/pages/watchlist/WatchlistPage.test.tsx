import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { WatchlistPage } from './WatchlistPage';
import { apiClient } from '../../api/client';
import type { Asset, AssetFundamentals, RecommendationRun } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

function makeFundamentals(
  overrides: Partial<AssetFundamentals> = {},
): AssetFundamentals {
  return {
    source: 'sec-edgar',
    status: 'available',
    cik: '0000320193',
    document: {
      figures: {
        revenue: { value: 400_000_000_000, unit: 'USD', period_end: '2023-09-30' },
        net_income: { value: 100_000_000_000, unit: 'USD', period_end: '2023-09-30' },
        eps_diluted: { value: 6.13, unit: 'USD/shares', period_end: '2023-09-30' },
      },
      company_details: {
        name: 'Example Corp',
        sicDescription: 'Electronic Computers',
        exchanges: ['Nasdaq'],
      },
    },
    fetched_at: '2026-10-05T00:00:00Z',
    ...overrides,
  };
}

function makeAsset(overrides: Partial<Asset> = {}): Asset {
  return {
    id: 1,
    ticker: 'EMERG',
    name: 'Example Corp',
    alpaca_symbol: 'EMERG',
    category: 'stock',
    sector: 'technology',
    exchange: 'NASDAQ',
    currency: 'USD',
    membership: 'watchlist',
    market_cap_usd: 1_000_000_000,
    avg_daily_turnover_usd: 1_000_000,
    history_years: 2,
    is_eligible: false,
    criteria_results: [],
    created_at: '2026-10-05T00:00:00Z',
    fundamentals: makeFundamentals(),
    ...overrides,
  };
}

function makeRun(overrides: Partial<RecommendationRun> = {}): RecommendationRun {
  return {
    id: 7,
    created_at: '2026-10-05T00:00:00Z',
    status: 'completed',
    requested_count: 3,
    requested_categories: ['stock'],
    prompt: 'p',
    tool_call_count: 1,
    results: [{ ticker: 'EMERG', outcome: 'added', detail: null }],
    error: null,
    target: 'watchlist',
    ...overrides,
  };
}

function renderPage(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('WatchlistPage', () => {
  it('lists watchlist entries with their fundamentals figures', async () => {
    mockedGet.mockResolvedValue({ data: { items: [makeAsset()], total: 1 } });

    renderPage(<WatchlistPage />);

    const heading = await screen.findByText('EMERG');
    const card = heading.closest('li') as HTMLElement;
    // The watchlist is fetched with an allowed page size (the backend rejects
    // any limit outside {20, 50, 100} with a 422), filtered to watchlist members.
    expect(mockedGet).toHaveBeenCalledWith(
      '/api/v1/assets',
      expect.objectContaining({
        params: expect.objectContaining({ membership: 'watchlist', limit: 100 }),
      }),
    );
    // Revenue is rendered compactly with its margin basis and derived margins.
    expect(within(card).getByText('Revenue')).toBeInTheDocument();
    expect(within(card).getByText(/\$400\.0B/)).toBeInTheDocument();
    // Net income margin = 100B / 400B = 25.0%.
    expect(within(card).getByText('25.0%')).toBeInTheDocument();
    // Company details surface.
    expect(within(card).getByText('Electronic Computers')).toBeInTheDocument();
    // An ineligible watchlist member is flagged, not hidden.
    expect(within(card).getByText(/Below universe bar/)).toBeInTheDocument();
  });

  it('indicates when an entry has unavailable fundamentals', async () => {
    const asset = makeAsset({
      id: 2,
      ticker: 'NOFACT',
      name: null,
      fundamentals: makeFundamentals({
        status: 'unavailable',
        cik: null,
        document: {},
      }),
    });
    mockedGet.mockResolvedValue({ data: { items: [asset], total: 1 } });

    renderPage(<WatchlistPage />);

    const heading = await screen.findByText('NOFACT');
    const card = heading.closest('li') as HTMLElement;
    expect(
      within(card).getByText(/Fundamentals unavailable/),
    ).toBeInTheDocument();
  });

  it('surfaces an error when the watchlist cannot be loaded', async () => {
    mockedGet.mockRejectedValue(new Error('boom'));

    renderPage(<WatchlistPage />);

    expect(
      await screen.findByText(/Could not load the watchlist/),
    ).toBeInTheDocument();
  });

  it('triggers a watchlist-targeted recommendation run', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.startsWith('/api/v1/recommendations')) {
        return Promise.resolve({ data: makeRun() });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });
    mockedPost.mockResolvedValue({ data: makeRun({ status: 'queued' }) });

    renderPage(<WatchlistPage />);

    await screen.findByText(/Your watchlist is empty/);

    await userEvent.click(screen.getByRole('button', { name: /discover/i }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/recommendations',
      expect.objectContaining({
        count: 3,
        categories: ['stock'],
        target: 'watchlist',
      }),
    );

    // The completed run's summary surfaces the added company.
    expect(
      await screen.findByText(/Added 1 company to your watchlist/),
    ).toBeInTheDocument();
  });
});
