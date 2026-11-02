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
  asset_id: 1,
  ticker: 'AAPL',
  label: 'Apple crossover',
  status: 'active',
  benchmark: 'SP500',
  initial_capital: 10000,
  allocated_capital: 10000,
  strategy_params: { fast_period: 20, slow_period: 50 },
  take_profit_pct: 0.2,
  stop_loss_pct: null,
  drawdown_stop_pct: 0.25,
  cash_buffer_pct: 0.02,
  peak_value: 10500,
  position_qty: 50,
  position_avg_price: 190,
  position_opened_at: '2026-10-02T13:35:00Z',
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
  allocated_capital: 10000,
  total_return: 325,
  total_return_pct: 0.0325,
  realised_pnl: 125,
  unrealised_pnl: 200,
  total_fees: 2,
  total_trades: 3,
  max_drawdown: 0.012,
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
    expect(screen.getByText('3.25%')).toBeInTheDocument(); // total return pct
    // Trade ledger row.
    const row = screen.getByText('fast SMA crossed above slow').closest('tr') as HTMLElement;
    expect(within(row).getByText('buy')).toBeInTheDocument();
    expect(within(row).getByText('filled')).toBeInTheDocument();
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
