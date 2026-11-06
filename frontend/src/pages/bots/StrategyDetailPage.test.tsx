import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { StrategyDetailPage } from './StrategyDetailPage';
import { apiClient } from '../../api/client';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const CATALOG = [
  {
    key: 'ma_crossover',
    display_name: 'MA Crossover',
    explanation:
      'Buys when the fast SMA crosses above the slow SMA. More detail follows here.',
    required_history: 51,
    params_schema: {},
  },
  {
    key: 'rsi_mean_reversion',
    display_name: 'RSI Mean Reversion',
    explanation:
      'Buys an oversold dip when RSI falls below the oversold level and exits as it reverts.',
    required_history: 15,
    params_schema: {},
  },
  {
    key: 'donchian_breakout',
    display_name: 'Donchian Range Breakout',
    explanation:
      'Buys an upward Donchian channel breakout; the Turtle version exits on a channel breakdown while the Locked version defers its exit to the engine.',
    required_history: 21,
    params_schema: {},
  },
];

function renderDetail(key: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/bots/strategies/${key}`]}>
        <Routes>
          <Route
            path="/bots/strategies/:key"
            element={<StrategyDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('StrategyDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the resolved explanation and the illustrative chart, without the capital/risk docs', async () => {
    mockedGet.mockResolvedValue({ data: CATALOG });

    renderDetail('ma_crossover');

    expect(
      await screen.findByText(/Buys when the fast SMA crosses above the slow SMA/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('img', {
        name: /crossover with entry and exit markers/i,
      }),
    ).toBeInTheDocument();
    // The strategy-agnostic docs live only on the index.
    expect(screen.queryByText('Shared budget ceiling')).not.toBeInTheDocument();
    expect(screen.queryByText('ATR position sizing')).not.toBeInTheDocument();
  });

  it('renders the RSI explanation and its illustrative chart', async () => {
    mockedGet.mockResolvedValue({ data: CATALOG });

    renderDetail('rsi_mean_reversion');

    expect(
      await screen.findByText(/Buys an oversold dip when RSI falls below/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('img', { name: /rsi mean-reversion/i }),
    ).toBeInTheDocument();
  });

  it('renders the Donchian explanation and its illustrative chart', async () => {
    mockedGet.mockResolvedValue({ data: CATALOG });

    renderDetail('donchian_breakout');

    expect(
      await screen.findByText(/Buys an upward Donchian channel breakout/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('img', { name: /donchian range breakout/i }),
    ).toBeInTheDocument();
  });

  it('shows a not-found state with a link back to the index for an unknown key', async () => {
    mockedGet.mockResolvedValue({ data: CATALOG });

    renderDetail('does_not_exist');

    expect(await screen.findByText(/Strategy not found/i)).toBeInTheDocument();
    const links = screen.getAllByRole('link');
    expect(
      links.some((l) => l.getAttribute('href') === '/bots/strategies'),
    ).toBe(true);
  });

  it('shows an error state when the catalog fails to load', async () => {
    mockedGet.mockRejectedValue(new Error('boom'));

    renderDetail('ma_crossover');

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });

  it('shows a loading state while the catalog is pending', () => {
    mockedGet.mockReturnValue(new Promise(() => {}));

    renderDetail('ma_crossover');

    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
