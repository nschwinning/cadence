import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { WatchlistPage } from './WatchlistPage';
import { apiClient } from '../../api/client';
import type { Asset, RecommendationRun } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

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
    fundamentals: null,
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
    model: 'gpt-5-mini',
    ...overrides,
  };
}

/**
 * Route `apiClient.get` by URL: the watchlist is listed via the shared assets
 * endpoint; recommendation-run polling hits a separate endpoint.
 */
function routeGet(assets: Asset[]) {
  mockedGet.mockImplementation((url: string) => {
    if (url.startsWith('/api/v1/recommendations')) {
      return Promise.resolve({ data: makeRun() });
    }
    return Promise.resolve({
      data: { items: assets, total: assets.length },
    });
  });
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
  it('lists watchlist rows fetched with membership=watchlist and links to detail', async () => {
    routeGet([makeAsset()]);

    renderPage(<WatchlistPage />);

    const link = await screen.findByRole('link', { name: 'EMERG' });
    // Rows link to the shared asset detail page.
    expect(link).toHaveAttribute('href', '/assets/EMERG');
    expect(screen.getByText('Example Corp')).toBeInTheDocument();
    // An ineligible watchlist member is flagged, not hidden.
    expect(screen.getByText(/Below universe bar/)).toBeInTheDocument();

    // The list is fetched via the shared assets path, filtered to watchlist
    // members, with an allowed page size.
    expect(mockedGet).toHaveBeenCalledWith(
      '/api/v1/assets',
      expect.objectContaining({
        params: expect.objectContaining({
          membership: 'watchlist',
          limit: 20,
        }),
      }),
    );
  });

  it('does not render fundamentals or technical values inline', async () => {
    routeGet([makeAsset()]);

    renderPage(<WatchlistPage />);

    await screen.findByRole('link', { name: 'EMERG' });
    // The table is a jump-off point: no inline fundamentals / technicals.
    expect(screen.queryByText('Revenue')).not.toBeInTheDocument();
    expect(screen.queryByText('RSI (14)')).not.toBeInTheDocument();
    // The per-asset technical endpoint is never hit from the list page.
    expect(mockedGet).not.toHaveBeenCalledWith(
      expect.stringContaining('/technical-indicators'),
    );
  });

  it('exposes search, sort, and filter controls wired to the query', async () => {
    routeGet([makeAsset()]);

    renderPage(<WatchlistPage />);

    await screen.findByRole('link', { name: 'EMERG' });

    // Filter dropdowns are present.
    expect(
      screen.getByRole('button', { name: /categories/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sectors/i })).toBeInTheDocument();

    // Sorting by name re-queries with the new sort field.
    await userEvent.click(screen.getByRole('button', { name: /name/i }));
    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith(
        '/api/v1/assets',
        expect.objectContaining({
          params: expect.objectContaining({ sort: 'name' }),
        }),
      );
    });

    // Searching re-queries with the (debounced) search term.
    await userEvent.type(screen.getByLabelText('Search watchlist'), 'emer');
    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith(
        '/api/v1/assets',
        expect.objectContaining({
          params: expect.objectContaining({ search: 'emer' }),
        }),
      );
    });
  });

  it('shows the empty state when the watchlist has no members', async () => {
    routeGet([]);

    renderPage(<WatchlistPage />);

    expect(
      await screen.findByText(/Your watchlist is empty/),
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
        // Defaults to the configured recommender model when unchanged.
        model: 'gpt-5-mini',
      }),
    );

    // The completed run's summary surfaces the added company.
    expect(
      await screen.findByText(/Added 1 company to your watchlist/),
    ).toBeInTheDocument();
  });
});
