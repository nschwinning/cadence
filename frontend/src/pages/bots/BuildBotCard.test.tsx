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
  {
    key: 'atr_band_supertrend_algo9',
    display_name: 'SuperTrend (Algo 9)',
    description: 'SuperTrend 20 / 3.',
    course_ref: 'Algo 9',
    strategy_key: 'atr_band_trend',
    strategy_params: { version: 'supertrend', window: 20, atr_mult: 3.0 },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.005,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'atr_band_keltner_algo21',
    display_name: 'Keltner Breakout (Algo 21)',
    description: 'Keltner 20 / 1.',
    course_ref: 'Algo 21',
    strategy_key: 'atr_band_trend',
    strategy_params: {
      version: 'keltner',
      window: 20,
      atr_mult: 1.0,
      exit_on_midline: true,
    },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.01,
    drawdown_stop_pct: 0.05,
    is_default: false,
  },
  {
    key: 'adx_trend_algo12',
    display_name: 'ADX Trend Strength (Algo 12)',
    description: 'ADX 10 / 20.',
    course_ref: 'Algo 12',
    strategy_key: 'adx_trend',
    strategy_params: { period: 10, threshold: 20 },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.01,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'rolling_reversion_vwap_adx_algo15',
    display_name: 'VWAP + ADX Reversion (Algo 15)',
    description: 'Typical-price cross with an ADX danger exit.',
    course_ref: 'Algo 15',
    strategy_key: 'rolling_average_reversion',
    strategy_params: {
      average_type: 'typical',
      window: 20,
      distance: 'band',
      entry_threshold: 0.0,
      exit_threshold: 0.005,
      entry_z: 1.0,
      exit_z: 0.2,
      exit_mode: 'bracket',
      adx_exit: true,
      adx_lookback: 20,
      adx_threshold: 20,
    },
    take_profit_pct: 0.005,
    stop_loss_pct: null,
    drawdown_stop_pct: 0.05,
    is_default: false,
  },
  {
    key: 'macd_momentum_algo10',
    display_name: 'MACD Momentum (Algo 10)',
    description: 'MACD 12 / 26 / 9.',
    course_ref: 'Algo 10',
    strategy_key: 'macd_momentum',
    strategy_params: { fast_period: 12, slow_period: 26, signal_period: 9 },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.005,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'heikin_ashi_algo11',
    display_name: 'Heikin-Ashi Trend (Algo 11)',
    description: 'Green in, red out.',
    course_ref: 'Algo 11',
    strategy_key: 'heikin_ashi_trend',
    strategy_params: { volume_filter: false },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.01,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'heikin_ashi_volume_algo37',
    display_name: 'Heikin-Ashi + Volume (Algo 37)',
    description: 'Green with volume.',
    course_ref: 'Algo 37',
    strategy_key: 'heikin_ashi_trend',
    strategy_params: { volume_filter: true, volume_window: 20 },
    take_profit_pct: null,
    stop_loss_pct: null,
    drawdown_stop_pct: 0.05,
    is_default: false,
  },
  {
    key: 'hma_trend_algo19',
    display_name: 'HMA Trend (Algos 19 / 26)',
    description: 'HMA 9 / 21.',
    course_ref: 'Algos 19, 26',
    strategy_key: 'hma_trend',
    strategy_params: { fast_period: 9, slow_period: 21 },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.01,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'ma_ribbon_algo18',
    display_name: 'MA Ribbon (Algo 18)',
    description: 'Ribbon 5 / 10 / 20.',
    course_ref: 'Algo 18',
    strategy_key: 'ma_ribbon',
    strategy_params: { fast_period: 5, mid_period: 10, slow_period: 20 },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.01,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'vama_algo30',
    display_name: 'VAMA (Algo 30)',
    description: 'Fixed smoothing as in the course.',
    course_ref: 'Algo 30',
    strategy_key: 'vama',
    strategy_params: { lookback: 20, alpha_min: 0.02, alpha_max: 0.2, adaptive: false },
    take_profit_pct: null,
    stop_loss_pct: null,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'price_velocity_algo48',
    display_name: 'Price Velocity Reversal (Algo 48)',
    description: 'Decelerating drop, 0.2%.',
    course_ref: 'Algo 48',
    strategy_key: 'price_velocity_reversal',
    strategy_params: { threshold_pct: 0.002 },
    take_profit_pct: 0.005,
    stop_loss_pct: 0.01,
    drawdown_stop_pct: 0.05,
    is_default: true,
  },
  {
    key: 'rolling_reversion_gradient_algo3',
    display_name: 'Gradient Convergence (Algo 3)',
    description: 'Below the 5-bar average in, back at it out.',
    course_ref: 'Algo 3',
    strategy_key: 'rolling_average_reversion',
    strategy_params: {
      average_type: 'sma',
      window: 5,
      distance: 'band',
      entry_threshold: 0.0,
      exit_threshold: 0.0,
      entry_z: 1.0,
      exit_z: 0.2,
      exit_mode: 'revert',
    },
    take_profit_pct: null,
    stop_loss_pct: null,
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
          {
            key: 'price_velocity_reversal',
            display_name: 'Price Velocity Reversal',
            explanation: 'Buys slowing sell-offs.',
            required_history: 3,
            params_schema: {},
          },
          {
            key: 'vama',
            display_name: 'VAMA',
            explanation: 'Buys above a volatility-adaptive average.',
            required_history: 80,
            params_schema: {},
          },
          {
            key: 'ma_ribbon',
            display_name: 'MA Ribbon',
            explanation: 'Buys when three averages stack upward.',
            required_history: 20,
            params_schema: {},
          },
          {
            key: 'hma_trend',
            display_name: 'HMA Trend',
            explanation: 'Rides rising Hull averages.',
            required_history: 25,
            params_schema: {},
          },
          {
            key: 'heikin_ashi_trend',
            display_name: 'Heikin-Ashi Trend',
            explanation: 'Rides green Heikin-Ashi runs.',
            required_history: 10,
            params_schema: {},
          },
          {
            key: 'macd_momentum',
            display_name: 'MACD Momentum',
            explanation: 'Buys bullish MACD crosses above zero.',
            required_history: 87,
            params_schema: {},
          },
          {
            key: 'adx_trend',
            display_name: 'ADX Trend Strength',
            explanation: 'Trades strong up-trends.',
            required_history: 20,
            params_schema: {},
          },
          {
            key: 'atr_band_trend',
            display_name: 'ATR-Band Trend',
            explanation: 'Rides breakouts of a volatility band.',
            required_history: 60,
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
      'VWAP + ADX Reversion (Algo 15)',
      'Gradient Convergence (Algo 3)',
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

  it('applies the SuperTrend preset when selecting ATR-Band Trend', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'atr_band_trend');

    await waitForPreset('SuperTrend (Algo 9)');
    expect(screen.getByLabelText('Version')).toHaveValue('supertrend');
    expect(screen.getByLabelText('Window')).toHaveValue(20);
    expect(screen.getByLabelText('ATR multiplier (×)')).toHaveValue(3);
    expect(
      screen.queryByLabelText('Exit when the close falls below the moving average'),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText('Stop-loss threshold (%)')).toHaveValue(0.5);
  });

  it('switching to Keltner applies the Algo 21 preset and submits its params', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'atr_band_trend');
    await waitForPreset('SuperTrend (Algo 9)');
    await user.selectOptions(screen.getByLabelText('Version'), 'keltner');

    await waitForPreset('Keltner Breakout (Algo 21)');
    expect(screen.getByLabelText('ATR multiplier (×)')).toHaveValue(1);
    expect(
      screen.getByLabelText('Exit when the close falls below the moving average'),
    ).toBeChecked();
    expect(screen.getByLabelText('Stop-loss threshold (%)')).toHaveValue(1);

    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'atr_band_trend',
          preset_key: 'atr_band_keltner_algo21',
          take_profit_pct: 0.005,
          stop_loss_pct: 0.01,
          strategy_params: {
            version: 'keltner',
            window: 20,
            atr_mult: 1,
            exit_on_midline: true,
          },
        }),
      );
    });
  });

  it('blocks ATR-Band submission with a non-positive multiplier', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'atr_band_trend');
    await waitForPreset('SuperTrend (Algo 9)');
    await pickAAPL(user);
    const mult = screen.getByLabelText('ATR multiplier (×)');
    await user.clear(mult);
    await user.type(mult, '0');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
  });

  it('applies the Algo 12 preset and submits the ADX params', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'adx_trend');

    await waitForPreset('ADX Trend Strength (Algo 12)');
    expect(screen.getByLabelText('ADX period')).toHaveValue(10);
    expect(screen.getByLabelText('ADX threshold')).toHaveValue(20);
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'adx_trend',
          preset_key: 'adx_trend_algo12',
          strategy_params: { period: 10, threshold: 20 },
        }),
      );
    });
  });

  it('applies the Algo 15 preset with the ADX danger exit and submits its fields', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'rolling_average_reversion');
    await waitForPreset('SMA Band Reversion (Algo 5)');
    expect(
      screen.getByLabelText('ADX danger exit: sell a losing trade in a strong downtrend'),
    ).not.toBeChecked();
    await user.selectOptions(screen.getByLabelText('Preset'), 'rolling_reversion_vwap_adx_algo15');

    await waitForPreset('VWAP + ADX Reversion (Algo 15)');
    expect(
      screen.getByLabelText('ADX danger exit: sell a losing trade in a strong downtrend'),
    ).toBeChecked();
    expect(screen.getByLabelText('ADX lookback (bars)')).toHaveValue(20);
    expect(screen.getByLabelText('Enable stop-loss')).not.toBeChecked();
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          preset_key: 'rolling_reversion_vwap_adx_algo15',
          stop_loss_pct: null,
          strategy_params: expect.objectContaining({
            average_type: 'typical',
            exit_mode: 'bracket',
            adx_exit: true,
            adx_lookback: 20,
            adx_threshold: 20,
          }),
        }),
      );
    });
  });

  it('switching back to Algo 5 turns the ADX danger exit off', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'rolling_average_reversion');
    await waitForPreset('SMA Band Reversion (Algo 5)');
    await user.selectOptions(screen.getByLabelText('Preset'), 'rolling_reversion_vwap_adx_algo15');
    await waitForPreset('VWAP + ADX Reversion (Algo 15)');
    await user.selectOptions(screen.getByLabelText('Preset'), 'rolling_reversion_sma_band_algo5');

    await waitForPreset('SMA Band Reversion (Algo 5)');
    expect(
      screen.getByLabelText('ADX danger exit: sell a losing trade in a strong downtrend'),
    ).not.toBeChecked();
  });

  it('applies the Algo 10 preset and submits the MACD params', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'macd_momentum');

    await waitForPreset('MACD Momentum (Algo 10)');
    expect(screen.getByLabelText('Fast EMA')).toHaveValue(12);
    expect(screen.getByLabelText('Slow EMA')).toHaveValue(26);
    expect(screen.getByLabelText('Signal EMA')).toHaveValue(9);
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'macd_momentum',
          preset_key: 'macd_momentum_algo10',
          strategy_params: { fast_period: 12, slow_period: 26, signal_period: 9 },
        }),
      );
    });
  });

  it('blocks MACD submission when the slow EMA is not above the fast one', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'macd_momentum');
    await waitForPreset('MACD Momentum (Algo 10)');
    await pickAAPL(user);
    const slow = screen.getByLabelText('Slow EMA');
    await user.clear(slow);
    await user.type(slow, '12');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
  });

  it('applies the Algo 11 preset and submits the filter off', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'heikin_ashi_trend');

    await waitForPreset('Heikin-Ashi Trend (Algo 11)');
    expect(
      screen.getByLabelText('Require above-average volume (and sell when it fades)'),
    ).not.toBeChecked();
    expect(screen.queryByLabelText('Volume window (bars)')).not.toBeInTheDocument();
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'heikin_ashi_trend',
          preset_key: 'heikin_ashi_algo11',
          strategy_params: { volume_filter: false },
        }),
      );
    });
  });

  it('applies the Algo 37 preset with the volume filter and submits its window', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'heikin_ashi_trend');
    await waitForPreset('Heikin-Ashi Trend (Algo 11)');
    await user.selectOptions(screen.getByLabelText('Preset'), 'heikin_ashi_volume_algo37');

    await waitForPreset('Heikin-Ashi + Volume (Algo 37)');
    expect(
      screen.getByLabelText('Require above-average volume (and sell when it fades)'),
    ).toBeChecked();
    expect(screen.getByLabelText('Volume window (bars)')).toHaveValue(20);
    expect(screen.getByLabelText('Enable take-profit')).not.toBeChecked();
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          preset_key: 'heikin_ashi_volume_algo37',
          take_profit_pct: null,
          strategy_params: { volume_filter: true, volume_window: 20 },
        }),
      );
    });
  });

  it('blocks Heikin-Ashi submission with a volume window below 2', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'heikin_ashi_trend');
    await waitForPreset('Heikin-Ashi Trend (Algo 11)');
    await pickAAPL(user);
    await user.click(
      screen.getByLabelText('Require above-average volume (and sell when it fades)'),
    );
    const window = screen.getByLabelText('Volume window (bars)');
    await user.clear(window);
    await user.type(window, '1');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
  });

  it('applies the HMA preset and submits its periods', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'hma_trend');

    await waitForPreset('HMA Trend (Algos 19 / 26)');
    expect(screen.getByLabelText('Fast HMA')).toHaveValue(9);
    expect(screen.getByLabelText('Slow HMA')).toHaveValue(21);
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'hma_trend',
          preset_key: 'hma_trend_algo19',
          strategy_params: { fast_period: 9, slow_period: 21 },
        }),
      );
    });
  });

  it('blocks HMA submission when the slow HMA is not above the fast one', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'hma_trend');
    await waitForPreset('HMA Trend (Algos 19 / 26)');
    await pickAAPL(user);
    const slow = screen.getByLabelText('Slow HMA');
    await user.clear(slow);
    await user.type(slow, '9');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
  });

  it('applies the MA Ribbon preset and submits its three periods', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'ma_ribbon');

    await waitForPreset('MA Ribbon (Algo 18)');
    expect(screen.getByLabelText('Fast SMA')).toHaveValue(5);
    expect(screen.getByLabelText('Mid SMA')).toHaveValue(10);
    expect(screen.getByLabelText('Slow SMA')).toHaveValue(20);
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'ma_ribbon',
          preset_key: 'ma_ribbon_algo18',
          strategy_params: { fast_period: 5, mid_period: 10, slow_period: 20 },
        }),
      );
    });
  });

  it('blocks MA Ribbon submission when the periods do not increase', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'ma_ribbon');
    await waitForPreset('MA Ribbon (Algo 18)');
    await pickAAPL(user);
    const mid = screen.getByLabelText('Mid SMA');
    await user.clear(mid);
    await user.type(mid, '5');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
  });

  it('applies the VAMA preset and submits all five params', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'vama');

    await waitForPreset('VAMA (Algo 30)');
    expect(screen.getByLabelText('Lookback (bars)')).toHaveValue(20);
    expect(screen.getByLabelText('Smoothing min (α)')).toHaveValue(0.02);
    expect(screen.getByLabelText('Smoothing max (α)')).toHaveValue(0.2);
    expect(
      screen.getByLabelText('Adaptive smoothing (faster when volatile, slower when calm)'),
    ).not.toBeChecked();
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'vama',
          preset_key: 'vama_algo30',
          take_profit_pct: null,
          stop_loss_pct: null,
          strategy_params: { lookback: 20, alpha_min: 0.02, alpha_max: 0.2, adaptive: false },
        }),
      );
    });
  });

  it('blocks VAMA submission when α min is not below α max', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'vama');
    await waitForPreset('VAMA (Algo 30)');
    await pickAAPL(user);
    const min = screen.getByLabelText('Smoothing min (α)');
    await user.clear(min);
    await user.type(min, '0.3');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
  });

  it('applies the Algo 48 preset with the threshold in percent and submits a fraction', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'price_velocity_reversal');

    await waitForPreset('Price Velocity Reversal (Algo 48)');
    expect(screen.getByLabelText('Velocity threshold (% per bar)')).toHaveValue(0.2);
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          strategy_key: 'price_velocity_reversal',
          preset_key: 'price_velocity_algo48',
          strategy_params: { threshold_pct: 0.002 },
        }),
      );
    });
  });

  it('blocks velocity submission with a non-positive threshold', async () => {
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'price_velocity_reversal');
    await waitForPreset('Price Velocity Reversal (Algo 48)');
    await pickAAPL(user);
    const threshold = screen.getByLabelText('Velocity threshold (% per bar)');
    await user.clear(threshold);
    await user.type(threshold, '0');

    expect(screen.getByRole('button', { name: 'Create bot' })).toBeDisabled();
  });

  it('applies the Algo 3 preset with equal zero thresholds and submits it', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();
    renderCard(<BuildBotCard />);

    await waitForPreset();
    await user.selectOptions(screen.getByLabelText('Strategy'), 'rolling_average_reversion');
    await waitForPreset('SMA Band Reversion (Algo 5)');
    await user.selectOptions(screen.getByLabelText('Preset'), 'rolling_reversion_gradient_algo3');

    await waitForPreset('Gradient Convergence (Algo 3)');
    expect(screen.getByLabelText('Window (bars)')).toHaveValue(5);
    expect(screen.getByLabelText('Entry below average (%)')).toHaveValue(0);
    expect(screen.getByLabelText('Exit within average (%)')).toHaveValue(0);
    await pickAAPL(user);
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({
          preset_key: 'rolling_reversion_gradient_algo3',
          take_profit_pct: null,
          stop_loss_pct: null,
          strategy_params: expect.objectContaining({
            window: 5,
            entry_threshold: 0,
            exit_threshold: 0,
            exit_mode: 'revert',
          }),
        }),
      );
    });
  });
});
