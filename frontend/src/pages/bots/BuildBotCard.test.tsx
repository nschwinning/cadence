import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { BuildBotCard } from './BuildBotCard';
import { apiClient } from '../../api/client';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

/** Route the catalog GETs the form issues on mount. */
function routeCatalogs() {
  mockedGet.mockImplementation((url: string) => {
    if (url.endsWith('/bots/strategies')) {
      return Promise.resolve({
        data: [
          {
            key: 'ma_crossover',
            display_name: 'MA Crossover',
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
    return Promise.resolve({ data: [] });
  });
}

function renderCard(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('BuildBotCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routeCatalogs();
  });

  it('renders the build form with its strategy, ticker and SMA period fields', async () => {
    renderCard(<BuildBotCard />);

    expect(
      await screen.findByRole('heading', { name: 'Build a bot' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Strategy')).toBeInTheDocument();
    expect(screen.getByLabelText('Ticker')).toBeInTheDocument();
    expect(screen.getByLabelText('Fast SMA period')).toHaveValue(20);
    expect(screen.getByLabelText('Slow SMA period')).toHaveValue(50);
  });

  it('submits strategy params and uppercased ticker, then confirms success', async () => {
    mockedPost.mockResolvedValue({ data: { id: 'b1' } });
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByLabelText('Ticker');
    await user.type(screen.getByLabelText('Ticker'), 'aapl');
    await user.click(screen.getByRole('button', { name: 'Create bot' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/api/v1/bots/sessions', {
        strategy_key: 'ma_crossover',
        ticker: 'AAPL',
        initial_capital: 10000,
        benchmark: 'SP500',
        strategy_params: { fast_period: 20, slow_period: 50 },
        label: null,
        take_profit_pct: null,
        stop_loss_pct: null,
      });
    });
    expect(await screen.findByText('Bot created')).toBeInTheDocument();
  });

  it('blocks submission when the fast period is not below the slow period', async () => {
    const user = userEvent.setup();

    renderCard(<BuildBotCard />);

    await screen.findByLabelText('Ticker');
    await user.type(screen.getByLabelText('Ticker'), 'AAPL');
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

    await screen.findByLabelText('Ticker');
    await user.type(screen.getByLabelText('Ticker'), 'AAPL');
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
