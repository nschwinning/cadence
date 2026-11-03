import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { AssetPicker } from './AssetPicker';
import { apiClient } from '../api/client';
import type { Asset } from '../types/api';

vi.mock('../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

function asset(id: number, ticker: string, name: string): Asset {
  return {
    id,
    ticker,
    name,
    alpaca_symbol: ticker,
    category: 'stock',
    sector: 'technology',
    exchange: 'NASDAQ',
    currency: 'USD',
    membership: 'universe',
    market_cap_usd: null,
    avg_daily_turnover_usd: null,
    history_years: null,
    is_eligible: true,
    criteria_results: [],
    created_at: '2026-01-01T00:00:00Z',
    fundamentals: null,
  };
}

/** Route /api/v1/assets to a search-aware result set (AAPL/MSFT, nothing for others). */
function routeAssets() {
  mockedGet.mockImplementation((_url, config) => {
    const params = (config?.params ?? {}) as { search?: string };
    const search = (params.search ?? '').toUpperCase();
    const all = [asset(1, 'AAPL', 'Apple'), asset(2, 'MSFT', 'Microsoft')];
    const items = all.filter((a) => a.ticker.includes(search) || search === '');
    return Promise.resolve({ data: { items, total: items.length } });
  });
}

/** Stateful harness exposing the picker's current selection as text. */
function Harness() {
  const [selected, setSelected] = useState<string[]>([]);
  const [whole, setWhole] = useState(false);
  return (
    <>
      <AssetPicker
        selected={selected}
        onChange={setSelected}
        wholeUniverse={whole}
        onWholeUniverseChange={setWhole}
      />
      <output data-testid="selected">{selected.join(',')}</output>
      <output data-testid="whole">{String(whole)}</output>
    </>
  );
}

function renderPicker() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Harness />
    </QueryClientProvider>,
  );
}

describe('AssetPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routeAssets();
  });

  it('shows typeahead results for a search term', async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.type(
      screen.getByRole('combobox', { name: 'Search universe equities' }),
      'AAPL',
    );

    expect(
      await screen.findByRole('button', { name: /AAPL/ }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith(
        '/api/v1/assets',
        expect.objectContaining({
          params: expect.objectContaining({
            search: 'AAPL',
            category: ['stock'],
            membership: 'universe',
          }),
        }),
      );
    });
  });

  it('multi-selects tickers and removes the chosen one from results', async () => {
    const user = userEvent.setup();
    renderPicker();

    const box = screen.getByRole('combobox', { name: 'Search universe equities' });
    await user.type(box, 'A');
    await user.click(await screen.findByRole('button', { name: /AAPL/ }));
    expect(screen.getByTestId('selected')).toHaveTextContent('AAPL');

    await user.type(box, 'M');
    await user.click(await screen.findByRole('button', { name: /MSFT/ }));
    expect(screen.getByTestId('selected')).toHaveTextContent('AAPL,MSFT');
  });

  it('selects the whole universe and hides the individual picker', async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.click(
      screen.getByLabelText('Trade the whole eligible universe'),
    );

    expect(screen.getByTestId('whole')).toHaveTextContent('true');
    expect(
      screen.queryByRole('combobox', { name: 'Search universe equities' }),
    ).not.toBeInTheDocument();
  });

  it('offers no option to submit a non-universe string', async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.type(
      screen.getByRole('combobox', { name: 'Search universe equities' }),
      'NOTREAL',
    );

    expect(
      await screen.findByText('No eligible universe equities match.'),
    ).toBeInTheDocument();
    // No clickable option is offered for an unmatched free-text string.
    expect(screen.queryByRole('button', { name: /NOTREAL/ })).toBeNull();
    expect(screen.queryByRole('option')).toBeNull();
    expect(screen.getByTestId('selected')).toHaveTextContent('');
  });
});
