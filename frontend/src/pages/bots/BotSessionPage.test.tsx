import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import { BotSessionPage } from './BotSessionPage';
import { apiClient } from '../../api/client';
import type { BotKpis, BotSession, BotTrade } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

const bot: BotSession = {
  id: 'b1',
  strategy_key: 'ma_crossover',
  label: 'Apple crossover',
  status: 'active',
  benchmark: 'SP500',
  initial_capital: 10000,
  allocated_capital: 10000,
  cash: 500,
  current_value: 10325,
  sizing_method: 'atr_risk',
  risk_pct: 0.01,
  atr_period: 14,
  atr_k: 2.0,
  max_position_pct: 0.25,
  max_positions: 10,
  strategy_params: { fast_period: 20, slow_period: 50 },
  take_profit_pct: 0.2,
  stop_loss_pct: null,
  drawdown_stop_pct: 0.25,
  cash_buffer_pct: 0.02,
  peak_value: 10500,
  symbols: [
    { asset_id: 1, ticker: 'AAPL', alpaca_symbol: 'AAPL' },
    { asset_id: 2, ticker: 'MSFT', alpaca_symbol: 'MSFT' },
  ],
  positions: [
    {
      asset_id: 1,
      ticker: 'AAPL',
      alpaca_symbol: 'AAPL',
      quantity: 50,
      avg_price: 190,
      opened_at: '2026-10-02T13:35:00Z',
    },
  ],
  total_trades: 3,
  realised_pnl: 125,
  total_fees: 2,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-05T00:00:00Z',
  last_tick_at: '2026-10-05T13:35:00Z',
  archived_at: null,
};

const kpis: BotKpis = {
  current_value: 10325,
  cash: 737,
  allocated_capital: 10000,
  total_return: 325,
  total_return_pct: 0.0325,
  realised_pnl: 125,
  unrealised_pnl: 200,
  total_fees: 2,
  total_trades: 3,
  max_drawdown: 0.012,
  sharpe_ratio: 1.42,
  best_trade: { ticker: 'AAPL', realised_pnl: 412 },
  worst_trade: { ticker: 'MSFT', realised_pnl: -88 },
  benchmark: 'SP500',
  benchmark_return_pct: 0.02,
  excess_return_pct: 0.0125,
};

const trade: BotTrade = {
  id: 't1',
  bot_session_id: 'b1',
  side: 'buy',
  ticker: 'AAPL',
  quantity: 50,
  filled_price: 190,
  fees: 1,
  reason: 'fast SMA crossed above slow',
  order_id: 'o1',
  status: 'filled',
  created_at: '2026-10-02T13:35:00Z',
};

/** Route every GET the detail page issues by URL suffix. */
function routeGet(overrides: { session?: BotSession } = {}) {
  return (url: string) => {
    if (url.endsWith('/kpis')) return Promise.resolve({ data: kpis });
    if (url.endsWith('/benchmarks'))
      return Promise.resolve({ data: [{ id: 'SP500', name: 'S&P 500' }] });
    if (url.endsWith('/value-history'))
      return Promise.resolve({ data: { items: [], total: 0 } });
    if (url.endsWith('/trades'))
      return Promise.resolve({ data: { items: [trade], total: 1 } });
    return Promise.resolve({ data: overrides.session ?? bot });
  };
}

function renderDetail(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/bots/b1']}>
        <Routes>
          <Route path="/bots/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('BotSessionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the header, KPI tiles and trade ledger for the bot', async () => {
    mockedGet.mockImplementation(routeGet());

    renderDetail(<BotSessionPage />);

    expect(
      await screen.findByRole('heading', { name: 'Apple crossover' }),
    ).toBeInTheDocument();
    // KPI tiles.
    expect(screen.getByText('$10,325.00')).toBeInTheDocument(); // current value
    expect(screen.getByText('Available cash')).toBeInTheDocument();
    expect(screen.getByText('$737.00')).toBeInTheDocument(); // available cash
    expect(screen.getByText('3.25%')).toBeInTheDocument(); // total return pct
    // Best/worst closed round-trip tiles.
    const best = screen.getByText('Best trade').closest('div') as HTMLElement;
    expect(within(best).getByText('$412.00')).toBeInTheDocument();
    expect(within(best).getByText('AAPL')).toBeInTheDocument();
    const worst = screen.getByText('Worst trade').closest('div') as HTMLElement;
    expect(within(worst).getByText('-$88.00')).toBeInTheDocument();
    expect(within(worst).getByText('MSFT')).toBeInTheDocument();
    // Benchmark-comparison tile replaces the (always-$0) transaction-fees tile.
    const benchmarkTile = (
      await screen.findByText('vs S&P 500')
    ).closest('div') as HTMLElement;
    expect(within(benchmarkTile).getByText('1.25%')).toBeInTheDocument(); // excess
    expect(
      within(benchmarkTile).getByText('Benchmark 2.00%, buy & hold'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Transaction fees')).not.toBeInTheDocument();
    // Trade ledger row.
    const row = screen.getByText('fast SMA crossed above slow').closest('tr') as HTMLElement;
    expect(within(row).getByText('buy')).toBeInTheDocument();
    expect(within(row).getByText('filled')).toBeInTheDocument();
  });

  it('renders the Sharpe ratio tile when a value is present', async () => {
    mockedGet.mockImplementation(routeGet());

    renderDetail(<BotSessionPage />);

    expect(await screen.findByText('Sharpe ratio')).toBeInTheDocument();
    expect(screen.getByText('1.42')).toBeInTheDocument();
    expect(screen.getByText('Annualised, from daily NAV')).toBeInTheDocument();
  });

  it('shows the not-yet-available Sharpe state when the value is null', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/kpis'))
        return Promise.resolve({ data: { ...kpis, sharpe_ratio: null } });
      if (url.endsWith('/value-history'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      if (url.endsWith('/trades'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      return Promise.resolve({ data: bot });
    });

    renderDetail(<BotSessionPage />);

    expect(await screen.findByText('Sharpe ratio')).toBeInTheDocument();
    expect(screen.getByText('Not yet available')).toBeInTheDocument();
    expect(screen.getByText('Needs more daily history')).toBeInTheDocument();
  });

  it('shows a no-closed-trades state when best/worst trade are absent', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/kpis'))
        return Promise.resolve({
          data: { ...kpis, best_trade: null, worst_trade: null },
        });
      if (url.endsWith('/value-history'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      if (url.endsWith('/trades'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      return Promise.resolve({ data: bot });
    });

    renderDetail(<BotSessionPage />);

    expect(await screen.findByText('Best trade')).toBeInTheDocument();
    expect(screen.getByText('Worst trade')).toBeInTheDocument();
    // Both tiles fall back to the empty state.
    expect(screen.getAllByText('No closed trades yet')).toHaveLength(2);
  });

  it('shows the benchmark tile placeholder when the comparison is unavailable', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/kpis'))
        return Promise.resolve({
          data: { ...kpis, benchmark_return_pct: null, excess_return_pct: null },
        });
      if (url.endsWith('/benchmarks'))
        return Promise.resolve({ data: [{ id: 'SP500', name: 'S&P 500' }] });
      if (url.endsWith('/value-history'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      if (url.endsWith('/trades'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      return Promise.resolve({ data: bot });
    });

    renderDetail(<BotSessionPage />);

    const benchmarkTile = (
      await screen.findByText('vs S&P 500')
    ).closest('div') as HTMLElement;
    expect(within(benchmarkTile).getByText('—')).toBeInTheDocument();
    expect(
      within(benchmarkTile).getByText('Needs a daily snapshot'),
    ).toBeInTheDocument();
  });

  it('sorts open positions by ticker by default and by opened timestamp on demand', async () => {
    // Ticker order (AAPL, MSFT) differs from opened order (MSFT earlier) so the
    // two sorts are distinguishable.
    const multi: BotSession = {
      ...bot,
      positions: [
        {
          asset_id: 1,
          ticker: 'AAPL',
          alpaca_symbol: 'AAPL',
          quantity: 50,
          avg_price: 190,
          opened_at: '2026-10-05T13:35:00Z',
        },
        {
          asset_id: 2,
          ticker: 'MSFT',
          alpaca_symbol: 'MSFT',
          quantity: 10,
          avg_price: 300,
          opened_at: '2026-10-02T13:35:00Z',
        },
      ],
    };
    mockedGet.mockImplementation(routeGet({ session: multi }));
    const user = userEvent.setup();

    renderDetail(<BotSessionPage />);

    const table = (await screen.findByText('Avg price')).closest(
      'table',
    ) as HTMLElement;
    const tickerOrder = () =>
      within(table)
        .getAllByRole('link')
        .map((a) => a.textContent);
    // Default: by ticker → AAPL before MSFT.
    expect(tickerOrder()).toEqual(['AAPL', 'MSFT']);

    // Switch to opened-timestamp order → MSFT (opened earlier) first.
    await user.selectOptions(screen.getByLabelText('Sort by'), 'opened');
    expect(tickerOrder()).toEqual(['MSFT', 'AAPL']);
  });

  it('paginates the trade ledger with Previous/Next controls', async () => {
    // 25 trades over a page size of 20 → two pages. Items differ by page so we
    // can tell which page is showing; total drives the "Page X of N" indicator.
    mockedGet.mockImplementation((url: string, config?: { params?: { offset?: number } }) => {
      if (url.endsWith('/kpis')) return Promise.resolve({ data: kpis });
      if (url.endsWith('/value-history'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      if (url.endsWith('/trades')) {
        const offset = config?.params?.offset ?? 0;
        const reason = offset === 0 ? 'page-one-trade' : 'page-two-trade';
        return Promise.resolve({
          data: { items: [{ ...trade, id: `t-${offset}`, reason }], total: 25 },
        });
      }
      return Promise.resolve({ data: bot });
    });
    const user = userEvent.setup();

    renderDetail(<BotSessionPage />);

    await screen.findByRole('heading', { name: 'Apple crossover' });
    // Page 1: indicator, Previous disabled, first-page content.
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    expect(await screen.findByText('page-one-trade')).toBeInTheDocument();

    // Advance → offset 20 requested, page 2 content, Next now disabled.
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByText('page-two-trade')).toBeInTheDocument();
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled();
    expect(mockedGet).toHaveBeenCalledWith(
      expect.stringContaining('/trades'),
      expect.objectContaining({ params: expect.objectContaining({ offset: 20 }) }),
    );
  });

  it('stops an active bot through the stop action', async () => {
    mockedGet.mockImplementation(routeGet());
    mockedPost.mockResolvedValue({ data: { ...bot, status: 'stopped' } });
    const user = userEvent.setup();

    renderDetail(<BotSessionPage />);

    await screen.findByRole('heading', { name: 'Apple crossover' });
    await user.click(screen.getByRole('button', { name: 'Stop' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/api/v1/bots/sessions/b1/stop', {});
    });
  });

  it('renders the open positions table for a multi-position bot', async () => {
    const multi: BotSession = {
      ...bot,
      positions: [
        {
          asset_id: 1,
          ticker: 'AAPL',
          alpaca_symbol: 'AAPL',
          quantity: 50,
          avg_price: 190,
          opened_at: '2026-10-02T13:35:00Z',
        },
        {
          asset_id: 2,
          ticker: 'MSFT',
          alpaca_symbol: 'MSFT',
          quantity: 10,
          avg_price: 300,
          opened_at: '2026-10-03T13:35:00Z',
        },
      ],
    };
    mockedGet.mockImplementation(routeGet({ session: multi }));

    renderDetail(<BotSessionPage />);

    await screen.findByRole('heading', { name: 'Open positions' });
    // Scope to the positions table via its distinctive "Avg price" column header
    // (the table body renders only after the session query resolves).
    const table = (await screen.findByText('Avg price')).closest(
      'table',
    ) as HTMLElement;
    expect(within(table).getByText('AAPL')).toBeInTheDocument();
    expect(within(table).getByText('MSFT')).toBeInTheDocument();
    expect(within(table).getByText('$190.00')).toBeInTheDocument();
  });

  it('offers Archive instead of Stop for a stopped bot', async () => {
    mockedGet.mockImplementation(
      routeGet({ session: { ...bot, status: 'stopped' } }),
    );

    renderDetail(<BotSessionPage />);

    await screen.findByRole('heading', { name: 'Apple crossover' });
    expect(screen.getByRole('button', { name: 'Archive' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
  });
});
