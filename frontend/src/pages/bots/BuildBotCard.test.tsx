import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { BuildBotCard } from './BuildBotCard';
import { apiClient } from '../../api/client';
import type { BotPreset } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

/** The course-recipe presets the backend catalog serves. */
const PRESETS: BotPreset[] = [
  {
    key: 'ma_crossover_algo6',
    display_name: 'MA Crossover (Algo 6)',
    description: 'Fast 5 / slow 12.',
    course_ref: 'Algo 6',
    strategy_key: 'ma_crossover',
    strategy_params: { fast_period: 5, slow_period: 12 },
    take_profit_pct: 0.01,
    stop_loss_pct: 0.02,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'rsi_mean_reversion_algo16',
    display_name: 'RSI Mean Reversion (Algo 16)',
    description: 'RSI 14 / 30 / 50.',
    course_ref: 'Algo 16',
    strategy_key: 'rsi_mean_reversion',
    strategy_params: { period: 14, oversold: 30, exit_level: 50 },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.01,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'donchian_turtle_algo25',
    display_name: 'Turtle Breakout (Algo 25)',
    description: 'Turtle 20 / 10.',
    course_ref: 'Algo 25',
    strategy_key: 'donchian_breakout',
    strategy_params: { version: 'turtle', entry_period: 20, exit_period: 10 },
    take_profit_pct: null,
    stop_loss_pct: null,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'donchian_smart_range_algo8',
    display_name: 'Smart Range Breakout (Algo 8)',
    description: 'Locked 20, padding 0.5.',
    course_ref: 'Algo 8',
    strategy_key: 'donchian_breakout',
    strategy_params: { version: 'locked', channel_period: 20, atr_padding_mult: 0.5 },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.02,
    drawdown_stop_pct: 0.05,
    is_default: false,
  },
  {
    key: 'rolling_reversion_sma_band_algo5',
    display_name: 'SMA Band Reversion (Algo 5)',
    description: 'SMA Band Reversion (Algo 5) recipe.',
    course_ref: 'Algo 5',
    strategy_key: 'rolling_average_reversion',
    strategy_params: {
      average_type: 'sma',
      window: 20,
      distance: 'band',
      entry_threshold: 0.01,
      exit_threshold: 0.005,
      entry_z: 1.0,
      exit_z: 0.2,
      exit_mode: 'revert',
    },
    take_profit_pct: null,
    stop_loss_pct: 0.02,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'rolling_reversion_zscore_algo4',
    display_name: 'Z-Score Reversion (Algo 4)',
    description: 'Z-Score Reversion (Algo 4) recipe.',
    course_ref: 'Algo 4',
    strategy_key: 'rolling_average_reversion',
    strategy_params: {
      average_type: 'sma',
      window: 20,
      distance: 'zscore',
      entry_threshold: 0.01,
      exit_threshold: 0.005,
      entry_z: 1.0,
      exit_z: 0.2,
      exit_mode: 'revert',
    },
    take_profit_pct: null,
    stop_loss_pct: 0.02,
    drawdown_stop_pct: 0.05,
    is_default: false,
  },
  {
    key: 'rolling_reversion_mean_cross_algo14',
    display_name: 'Mean Cross Reversion (Algo 14)',
    description: 'Mean Cross Reversion (Algo 14) recipe.',
    course_ref: 'Algo 14',
    strategy_key: 'rolling_average_reversion',
    strategy_params: {
      average_type: 'sma',
      window: 60,
      distance: 'band',
      entry_threshold: 0.0,
      exit_threshold: 0.005,
      entry_z: 1.0,
      exit_z: 0.2,
      exit_mode: 'bracket',
    },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.01,
    drawdown_stop_pct: 0.05,
    is_default: false,
  },
  {
    key: 'rolling_reversion_vwap_cross_algo39',
    display_name: 'VWAP Cross Reversion (Algo 39)',
    description: 'VWAP Cross Reversion (Algo 39) recipe.',
    course_ref: 'Algo 39',
    strategy_key: 'rolling_average_reversion',
    strategy_params: {
      average_type: 'vwap',
      window: 60,
      distance: 'band',
      entry_threshold: 0.0,
      exit_threshold: 0.005,
      entry_z: 1.0,
      exit_z: 0.2,
      exit_mode: 'bracket',
    },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.01,
    drawdown_stop_pct: 0.05,
    is_default: false,
  },
];

/** Route the catalog GETs the form issues on mount plus the picker's asset search. */
function routeCatalogs({ presetsFail = false }: { presetsFail?: boolean } = {}) {
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
          {
            key: 'rolling_average_reversion',
            display_name: 'Rolling-Average Reversion',
            explanation: 'Buys dips below the rolling average.',
            required_history: 20,
            params_schema: {},
          },
        ],
      });
    }
    if (url.endsWith('/bots/presets')) {
      return presetsFail
        ? Promise.reject(new Error('presets unavailable'))
        : Promise.resolve({ data: PRESETS });
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

/**
 * Wait until the preset catalog has loaded and `name` is the applied preset — shown
 * in the preset selector for multi-preset strategies, else in the indicator line.
 * Returns the indicator (which carries the Customized marker).
 */
async function waitForPreset(name = 'MA Crossover (Algo 6)') {
  const indicator = await screen.findByTestId('bot-preset-indicator');
  await waitFor(() => {
    const selector = screen.queryByLabelText('Preset') as HTMLSelectElement | null;
    if (selector) {
      expect(selector.selectedOptions[0]?.textContent).toBe(name);
    } else {
      expect(indicator).toHaveTextContent(name);
    }
  });
  return indicator;
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
    await waitForPreset();
    expect(screen.getByLabelText('Fast SMA period')).toHaveValue(5);
  });

  it('preloads the MA Crossover course recipe (5/12, TP 1%, SL 2%, drawdown 5%)', async () => {
    renderCard(<BuildBotCard />);

    await waitForPreset();
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

    await waitForPreset();
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
  it('opens with the default preset applied and not customized', async () => {
    renderCard(<BuildBotCard />);

    const indicator = await waitForPreset();
    expect(indicator).not.toHaveTextContent('Customized');
  });

  it('applies the RSI default preset when switching strategy', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'rsi_mean_reversion');

    await waitForPreset('RSI Mean Reversion (Algo 16)');
    expect(screen.getByLabelText('RSI period')).toHaveValue(14);
    expect(screen.getByLabelText('Oversold level')).toHaveValue(30);
    expect(screen.getByLabelText('Exit level')).toHaveValue(50);
  });

  it('applies the Algo 8 preset when switching the Donchian version to Locked', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'donchian_breakout');
    await waitForPreset('Turtle Breakout (Algo 25)');
    // The Turtle preset ships with no take-profit / stop-loss bracket.
    expect(screen.getByLabelText('Enable take-profit')).not.toBeChecked();
    expect(screen.getByLabelText('Enable stop-loss')).not.toBeChecked();

    await user.selectOptions(screen.getByLabelText('Version'), 'locked');
    await waitForPreset('Smart Range Breakout (Algo 8)');
    expect(screen.getByLabelText('Channel period')).toHaveValue(20);
    expect(screen.getByLabelText('ATR padding (×)')).toHaveValue(0.5);
    expect(screen.getByLabelText('Take-profit threshold (%)')).toHaveValue(0.5);
    expect(screen.getByLabelText('Stop-loss threshold (%)')).toHaveValue(2);
  });

  it('marks the configuration customized on edit and clears it on revert', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    const indicator = await waitForPreset();
    const fast = screen.getByLabelText('Fast SMA period');
    await user.clear(fast);
    await user.type(fast, '7');
    expect(indicator).toHaveTextContent('Customized');

    await user.clear(fast);
    await user.type(fast, '5');
    expect(indicator).not.toHaveTextContent('Customized');
  });

  it('resets a customized configuration back to the preset', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    const indicator = await waitForPreset();
    await user.click(screen.getByLabelText('Enable stop-loss'));
    expect(indicator).toHaveTextContent('Customized');

    await user.click(screen.getByRole('button', { name: 'Reset to preset' }));
    expect(screen.getByLabelText('Enable stop-loss')).toBeChecked();
    expect(indicator).not.toHaveTextContent('Customized');
  });

  it('sends the applied preset key with the create request', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          preset_key: 'ma_crossover_algo6',
          strategy_key: 'ma_crossover',
        }),
      );
    });
  });

  it('keeps submit disabled and shows an error when presets fail to load', async () => {
    const user = userEvent.setup();
    routeCatalogs({ presetsFail: true });
    renderCard(<BuildBotCard />);

    expect(
      await screen.findByText('Could not load the strategy presets. Reload to try again.'),
    ).toBeInTheDocument();
    await pickAAPL(user);
    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
  });
  it('applies the Algo 5 preset when selecting Rolling-Average Reversion', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'rolling_average_reversion',
    );

    await waitForPreset('SMA Band Reversion (Algo 5)');
    expect(screen.getByLabelText('Average')).toHaveValue('sma');
    expect(screen.getByLabelText('Window (bars)')).toHaveValue(20);
    expect(screen.getByLabelText('Distance')).toHaveValue('band');
    expect(screen.getByLabelText('Entry below average (%)')).toHaveValue(1);
    expect(screen.getByLabelText('Exit within average (%)')).toHaveValue(0.5);
    expect(screen.getByLabelText('Exit')).toHaveValue('revert');
    expect(screen.getByLabelText('Enable take-profit')).not.toBeChecked();
    expect(screen.getByLabelText('Stop-loss threshold (%)')).toHaveValue(2);
  });

  it('shows the z-score fields when the distance is switched to z-score', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'rolling_average_reversion',
    );
    await waitForPreset('SMA Band Reversion (Algo 5)');
    await user.selectOptions(screen.getByLabelText('Distance'), 'zscore');

    expect(screen.getByLabelText('Entry z-score (σ below)')).toHaveValue(1);
    expect(screen.getByLabelText('Exit z-score (σ below)')).toHaveValue(0.2);
    expect(
      screen.queryByLabelText('Entry below average (%)'),
    ).not.toBeInTheDocument();
  });

  it('lists the reversion presets and applies Algo 39 from the selector', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'rolling_average_reversion',
    );
    const selector = (await screen.findByLabelText('Preset')) as HTMLSelectElement;
    expect(Array.from(selector.options).map((o) => o.textContent)).toEqual([
      'SMA Band Reversion (Algo 5)',
      'Z-Score Reversion (Algo 4)',
      'Mean Cross Reversion (Algo 14)',
      'VWAP Cross Reversion (Algo 39)',
    ]);

    await user.selectOptions(selector, 'rolling_reversion_vwap_cross_algo39');
    const indicator = await waitForPreset('VWAP Cross Reversion (Algo 39)');
    expect(screen.getByLabelText('Average')).toHaveValue('vwap');
    expect(screen.getByLabelText('Window (bars)')).toHaveValue(60);
    expect(screen.getByLabelText('Entry below average (%)')).toHaveValue(0);
    expect(screen.getByLabelText('Exit')).toHaveValue('bracket');
    expect(screen.getByLabelText('Take-profit threshold (%)')).toHaveValue(0.5);
    expect(screen.getByLabelText('Stop-loss threshold (%)')).toHaveValue(1);
    expect(indicator).not.toHaveTextContent('Customized');
  });

  it('submits all eight reversion params with band thresholds as fractions', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'rolling_average_reversion',
    );
    await waitForPreset('SMA Band Reversion (Algo 5)');
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'rolling_average_reversion',
          preset_key: 'rolling_reversion_sma_band_algo5',
          stop_loss_pct: 0.02,
          take_profit_pct: null,
          strategy_params: {
            average_type: 'sma',
            window: 20,
            distance: 'band',
            entry_threshold: 0.01,
            exit_threshold: 0.005,
            entry_z: 1,
            exit_z: 0.2,
            exit_mode: 'revert',
          },
        }),
      );
    });
  });

  it('blocks reversion submission when the revert exit is not below the entry', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(
      screen.getByLabelText('Strategy'),
      'rolling_average_reversion',
    );
    await waitForPreset('SMA Band Reversion (Algo 5)');
    await pickAAPL(user);
    const exit = screen.getByLabelText('Exit within average (%)');
    await user.clear(exit);
    await user.type(exit, '2');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
    expect(exit).toHaveAttribute('aria-invalid', 'true');
  });

  it('offers a Donchian preset selector that keeps the version in sync', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'donchian_breakout');
    await waitForPreset('Turtle Breakout (Algo 25)');

    await user.selectOptions(
      screen.getByLabelText('Preset'),
      'donchian_smart_range_algo8',
    );
    await waitForPreset('Smart Range Breakout (Algo 8)');
    expect(screen.getByLabelText('Version')).toHaveValue('locked');
    expect(screen.getByLabelText('Channel period')).toHaveValue(20);
  });

  it('shows no preset selector for a single-preset strategy', async () => {
    renderCard(<BuildBotCard />);

    await waitForPreset();
    expect(screen.queryByLabelText('Preset')).not.toBeInTheDocument();
  });
});
