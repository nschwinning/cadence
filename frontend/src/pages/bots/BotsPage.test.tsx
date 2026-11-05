import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { BotsPage } from './BotsPage';
import { apiClient } from '../../api/client';
import type { BotSession } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const bot: BotSession = {
  id: 'b1',
  strategy_key: 'ma_crossover',
  label: 'Apple crossover',
  status: 'active',
  benchmark: 'SP500',
  initial_capital: 10000,
  allocated_capital: 10000,
  cash: 10000,
  current_value: 10250,
  eod_value: 10200,
  sizing_method: 'atr_risk',
  risk_pct: 0.01,
  atr_period: 14,
  atr_k: 2.0,
  max_position_pct: 0.25,
  max_positions: 10,
  strategy_params: { fast_period: 20, slow_period: 50 },
  take_profit_pct: null,
  stop_loss_pct: null,
  drawdown_stop_pct: 0.25,
  cash_buffer_pct: 0.02,
  peak_value: 10000,
  symbols: [{ asset_id: 1, ticker: 'AAPL', alpaca_symbol: 'AAPL' }],
  positions: [],
  total_trades: 3,
  realised_pnl: 125,
  total_fees: 2,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-05T00:00:00Z',
  last_tick_at: '2026-10-05T13:35:00Z',
  archived_at: null,
};

/** Route a mocked GET to the bot catalog (strategies) vs. the sessions list. */
function routeGet(bots: BotSession[]) {
  return (url: string) => {
    if (url.endsWith('/bots/strategies')) {
      return Promise.resolve({ data: [] });
    }
    if (url.endsWith('/benchmarks')) {
      return Promise.resolve({ data: [{ id: 'SP500', name: 'S&P 500' }] });
    }
    return Promise.resolve({ data: { items: bots, total: bots.length } });
  };
}

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

describe('BotsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a bot row linking to its detail page', async () => {
    mockedGet.mockImplementation(routeGet([bot]));

    renderWithClient(<BotsPage />);

    const link = await screen.findByRole('link', { name: 'Apple crossover' });
    expect(link).toHaveAttribute('href', '/bots/b1');
    const row = link.closest('tr') as HTMLElement;
    expect(within(row).getByText('active')).toBeInTheDocument();
    expect(within(row).getByText('3')).toBeInTheDocument();
    expect(within(row).getByText('$125.00')).toBeInTheDocument();
    // The row shows both the live value and the end-of-day snapshot value,
    // not the allocated-capital baseline.
    expect(within(row).getByText('$10,250.00')).toBeInTheDocument(); // live
    expect(within(row).getByText('$10,200.00')).toBeInTheDocument(); // end of day
    expect(within(row).queryByText('$10,000.00')).not.toBeInTheDocument();
  });

  it('shows an em dash for a bot without an end-of-day snapshot', async () => {
    mockedGet.mockImplementation(routeGet([{ ...bot, eod_value: null }]));

    renderWithClient(<BotsPage />);

    const link = await screen.findByRole('link', { name: 'Apple crossover' });
    const row = link.closest('tr') as HTMLElement;
    expect(within(row).getByText('$10,250.00')).toBeInTheDocument(); // live
    expect(within(row).getByText('—')).toBeInTheDocument();
  });

  it('labels the value columns "Live value" and "End of day"', async () => {
    mockedGet.mockImplementation(routeGet([bot]));

    renderWithClient(<BotsPage />);

    await screen.findByRole('link', { name: 'Apple crossover' });
    expect(
      screen.getByRole('columnheader', { name: 'Live value' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', { name: 'End of day' }),
    ).toBeInTheDocument();
  });

  it('falls back to strategy + ticker when the bot has no label', async () => {
    mockedGet.mockImplementation(routeGet([{ ...bot, label: null }]));

    renderWithClient(<BotsPage />);

    const link = await screen.findByRole('link', {
      name: 'ma_crossover · AAPL',
    });
    expect(link).toHaveAttribute('href', '/bots/b1');
  });

  it('opens the build form in a modal only after the trigger is activated', async () => {
    mockedGet.mockImplementation(routeGet([bot]));
    const user = userEvent.setup();

    renderWithClient(<BotsPage />);

    await screen.findByRole('link', { name: 'Apple crossover' });
    expect(
      screen.queryByRole('heading', { name: 'Build a bot' }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Build a bot' }));

    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByRole('heading', { name: 'Build a bot' }),
    ).toBeInTheDocument();
  });

  it('toggling "Show archived" refetches with include_archived', async () => {
    mockedGet.mockImplementation(routeGet([bot]));
    const user = userEvent.setup();

    renderWithClient(<BotsPage />);
    await screen.findByRole('link', { name: 'Apple crossover' });

    expect(mockedGet).toHaveBeenCalledWith('/api/v1/bots/sessions', {
      params: {},
    });

    await user.click(screen.getByLabelText(/Show archived/i));

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith('/api/v1/bots/sessions', {
        params: { include_archived: true },
      });
    });
  });

  it('shows an empty state with no bots', async () => {
    mockedGet.mockImplementation(routeGet([]));

    renderWithClient(<BotsPage />);

    expect(await screen.findByText(/No bots yet/i)).toBeInTheDocument();
  });
});
