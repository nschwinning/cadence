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
          {
            key: 'rsi_mean_reversion',
            display_name: 'RSI Mean Reversion',
            explanation: 'Buys oversold dips.',
            required_history: 15,
            params_schema: {},
          },
          {
            key: 'donchian_breakout',
            display_name: 'Donchian Range Breakout',
            explanation: 'Buys upward channel breakouts.',
            required_history: 21,
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
    expect(screen.getByLabelText('Fast SMA period')).toHaveValue(5);
  });

  it('preloads the MA Crossover course recipe (5/12, TP 1%, SL 2%, drawdown 5%)', async () => {
    renderCard(<BuildBotCard />);

    await screen.findByRole('combobox', { name: 'Search universe equities' });
    expect(screen.getByLabelText('Fast SMA period')).toHaveValue(5);
    expect(screen.getByLabelText('Slow SMA period')).toHaveValue(12);
    // Take-profit and stop-loss are on by default, at the course percentages.
    expect(screen.getByLabelText('Enable take-profit')).toBeChecked();
    expect(screen.getByLabelText('Take-profit threshold (%)')).toHaveValue(1);
    expect(screen.getByLabelText('Enable stop-loss')).toBeChecked();
    expect(screen.getByLabelText('Stop-loss threshold (%)')).toHaveValue(2);
    expect(screen.getByLabelText('Drawdown kill-switch (%)')).toHaveValue(5);
  });

  it('re-applies the RSI course risk recipe when switching strategy', async () => {
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('option', { name: 'RSI Mean Reversion' });
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'rsi_mean_reversion',
    );

    // RSI (course Algo 16) uses TP 0.5% / SL 1% / drawdown 5%.
    expect(screen.getByLabelText('Enable take-profit')).toBeChecked();
    expect(screen.getByLabelText('Take-profit threshold (%)')).toHaveValue(0.5);
    expect(screen.getByLabelText('Enable stop-loss')).toBeChecked();
    expect(screen.getByLabelText('Stop-loss threshold (%)')).toHaveValue(1);
    expect(screen.getByLabelText('Drawdown kill-switch (%)')).toHaveValue(5);
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
          strategy_params: { fast_period: 5, slow_period: 12 },
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

  it('sends the default-on take-profit threshold as a fraction', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('combobox', { name: 'Search universe equities' });
    await pickAAPL(user);
    // Take-profit is preloaded on at the MA Crossover course value (1% → 0.01).
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({ take_profit_pct: 0.01 }),
      );
    });
  });

  it('sends a null take-profit when the default-on control is disabled', async () => {
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
        expect.objectContaining({ take_profit_pct: null }),
      );
    });
  });

  it('defaults the drawdown kill-switch to the course 5% and sends it as a fraction', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('combobox', { name: 'Search universe equities' });
    expect(screen.getByLabelText('Drawdown kill-switch (%)')).toHaveValue(5);

    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({ drawdown_stop_pct: 0.05 }),
      );
    });
  });

  it('blocks submission when the drawdown kill-switch is out of range', async () => {
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('combobox', { name: 'Search universe equities' });
    await pickAAPL(user);
    const drawdown = screen.getByLabelText('Drawdown kill-switch (%)');
    await user.clear(drawdown);
    await user.type(drawdown, '150');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
    expect(drawdown).toHaveAttribute('aria-invalid', 'true');
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('shows the RSI params (and hides the SMA params) when RSI is selected', async () => {
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('option', { name: 'RSI Mean Reversion' });
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'rsi_mean_reversion',
    );

    expect(screen.getByLabelText('RSI period')).toHaveValue(14);
    expect(screen.getByLabelText('Oversold level')).toHaveValue(30);
    expect(screen.getByLabelText('Exit level')).toHaveValue(50);
    expect(screen.queryByLabelText('Fast SMA period')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Slow SMA period')).not.toBeInTheDocument();
  });

  it('submits the RSI strategy with its params payload', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('option', { name: 'RSI Mean Reversion' });
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'rsi_mean_reversion',
    );
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'rsi_mean_reversion',
          strategy_params: { period: 14, oversold: 30, exit_level: 50 },
        }),
      );
    });
  });

  it('blocks RSI submission when oversold is not below the exit level', async () => {
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('option', { name: 'RSI Mean Reversion' });
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'rsi_mean_reversion',
    );
    await pickAAPL(user);
    const oversold = screen.getByLabelText('Oversold level');
    await user.clear(oversold);
    await user.type(oversold, '60');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
    expect(oversold).toHaveAttribute('aria-invalid', 'true');
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('shows the Donchian version selector and Turtle params (hiding SMA) when selected', async () => {
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('option', { name: 'Donchian Range Breakout' });
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'donchian_breakout',
    );

    expect(screen.getByLabelText('Version')).toHaveValue('turtle');
    expect(screen.getByLabelText('Entry channel period')).toHaveValue(20);
    expect(screen.getByLabelText('Exit channel period')).toHaveValue(10);
    expect(screen.queryByLabelText('Fast SMA period')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Channel period')).not.toBeInTheDocument();
  });

  it('swaps to the Locked params and re-applies its course recipe when the version changes', async () => {
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('option', { name: 'Donchian Range Breakout' });
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'donchian_breakout',
    );

    // Turtle ships with TP / SL off (it has its own channel exit).
    expect(screen.getByLabelText('Enable take-profit')).not.toBeChecked();
    expect(screen.getByLabelText('Enable stop-loss')).not.toBeChecked();

    await user.selectOptions(screen.getByLabelText('Version'), 'locked');

    expect(screen.getByLabelText('Channel period')).toHaveValue(20);
    expect(screen.getByLabelText('ATR padding (×)')).toHaveValue(0.5);
    expect(
      screen.queryByLabelText('Entry channel period'),
    ).not.toBeInTheDocument();
    // Locked defers its exit to the engine bracket → course TP 0.5% / SL 2% on.
    expect(screen.getByLabelText('Enable take-profit')).toBeChecked();
    expect(screen.getByLabelText('Take-profit threshold (%)')).toHaveValue(0.5);
    expect(screen.getByLabelText('Enable stop-loss')).toBeChecked();
    expect(screen.getByLabelText('Stop-loss threshold (%)')).toHaveValue(2);
  });

  it('submits the Turtle version with its params payload', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('option', { name: 'Donchian Range Breakout' });
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'donchian_breakout',
    );
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'donchian_breakout',
          strategy_params: {
            version: 'turtle',
            entry_period: 20,
            exit_period: 10,
          },
        }),
      );
    });
  });

  it('submits the Locked version with its params payload', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('option', { name: 'Donchian Range Breakout' });
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'donchian_breakout',
    );
    await user.selectOptions(screen.getByLabelText('Version'), 'locked');
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'donchian_breakout',
          strategy_params: {
            version: 'locked',
            channel_period: 20,
            atr_padding_mult: 0.5,
          },
        }),
      );
    });
  });

  it('blocks Turtle submission when the exit period is not below the entry period', async () => {
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByRole('option', { name: 'Donchian Range Breakout' });
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'donchian_breakout',
    );
    await pickAAPL(user);
    const exit = screen.getByLabelText('Exit channel period');
    await user.clear(exit);
    await user.type(exit, '30');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
    expect(exit).toHaveAttribute('aria-invalid', 'true');
    expect(mockedPost).not.toHaveBeenCalled();
  });
});
