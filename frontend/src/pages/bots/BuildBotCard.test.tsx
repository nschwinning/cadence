import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { BuildBotCard } from './BuildBotCard';
import { apiClient } from '../../api/client';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

/** Route the catalog GETs the form issues on mount plus the picker's asset search. */
function routeCatalogs() {
  mockedGet.mockImplementation((url: string) => {
    if (url.endsWith('/bots/strategies')) {
      return Promise.resolve({
        data: [
          {
            key: 'ma_crossover',
            display_name: 'MA Crossover',
            explanation: 'Fast crosses slow.',
            required_history: 51,
            params_schema: {},
          },
        ],
      });
    }
    if (url.endsWith('/benchmarks')) {
      return Promise.resolve({
        data: [{ id: 'SP500', name: 'S&P 500' }],
      });
    }
    if (url.endsWith('/assets')) {
      return Promise.resolve({
        data: {
          items: [
            {
              id: 1,
              ticker: 'AAPL',
              name: 'Apple',
              alpaca_symbol: 'AAPL',
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
            },
          ],
          total: 1,
        },
      });
    }
    return Promise.resolve({ data: [] });
  });
}

function renderCard(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Type into the picker and choose the AAPL option it returns. */
async function pickAAPL(user: ReturnType<typeof userEvent.setup>) {
  await user.type(
    screen.getByRole('combobox', { name: 'Search universe equities' }),
    'AAPL',
  );
  const option = await screen.findByRole('button', { name: /AAPL/ });
  await user.click(option);
}

describe('BuildBotCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routeCatalogs();
  });

  it('renders the build form with its strategy, picker and sizing fields', async () => {
    renderCard(<BuildBotCard />);

    expect(
      await screen.findByRole('heading', { name: 'Build a bot' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Strategy')).toBeInTheDocument();
    expect(
      screen.getByRole('combobox', { name: 'Search universe equities' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Sizing method')).toBeInTheDocument();
    expect(screen.getByLabelText('Max concurrent positions')).toHaveValue(10);
    expect(screen.getByLabelText('Fast SMA period')).toHaveValue(20);
  });

  it('submits a symbol set and ATR sizing params, then navigates away', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('combobox', { name: 'Search universe equities' });
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'ma_crossover',
          tickers: ['AAPL'],
          whole_universe: false,
          initial_capital: 10000,
          benchmark: 'SP500',
          sizing_method: 'atr_risk',
          risk_pct: 0.01,
          atr_period: 14,
          atr_k: 2,
          max_position_pct: 0.25,
          max_positions: 10,
          strategy_params: { fast_period: 20, slow_period: 50 },
        }),
      );
    });
  });

  it('submits whole_universe with a null ticker set', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByText('Trade the whole eligible universe');
    await user.click(screen.getByLabelText('Trade the whole eligible universe'));
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({ whole_universe: true, tickers: null }),
      );
    });
  });

  it('blocks submission until at least one symbol is chosen', async () => {
    renderCard(<BuildBotCard />);

    await screen.findByRole('combobox', { name: 'Search universe equities' });
    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
  });

  it('blocks submission when the fast period is not below the slow period', async () => {
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('combobox', { name: 'Search universe equities' });
    await pickAAPL(user);
    const fast = screen.getByLabelText('Fast SMA period');
    await user.clear(fast);
    await user.type(fast, '60');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
    expect(fast).toHaveAttribute('aria-invalid', 'true');
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('sends the take-profit threshold as a fraction when enabled', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('combobox', { name: 'Search universe equities' });
    await pickAAPL(user);
    await user.click(screen.getByLabelText('Enable take-profit'));
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({ take_profit_pct: 0.2 }),
      );
    });
  });
});
