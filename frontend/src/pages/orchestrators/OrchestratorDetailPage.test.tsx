import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { OrchestratorDetailPage } from './OrchestratorDetailPage';
import { apiClient } from '../../api/client';
import type {
  BotOrchestratorDetail,
  OrchestratorRunSummary,
} from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

const partialRun: OrchestratorRunSummary = {
  id: 'r1',
  trigger: 'scheduled',
  status: 'partial',
  model: 'gpt-6-luna',
  created_at: '2026-11-10T14:00:00Z',
  started_at: '2026-11-10T14:00:01Z',
  finished_at: '2026-11-10T14:01:00Z',
  duration_ms: 59000,
  error: null,
  market_summary: 'Tech breadth is improving; energy is rolling over.',
  applied: [
    {
      kind: 'deploy',
      bot_id: 'b2',
      preset_key: 'donchian_turtle_algo25',
      tickers: ['MSFT'],
      capital: 2500,
      rationale: 'Fresh 20-day high on strong breadth.',
    },
  ],
  rejected: [
    {
      kind: 'deploy',
      action: {
        preset_key: 'ma_crossover_algo6',
        tickers: ['XOM'],
        capital: 9000,
        rationale: 'x',
      },
      reason: 'capital 9,000.00 exceeds the free capital of 4,000.00',
    },
  ],
  usage: { requests: 2, input_tokens: 1000, output_tokens: 234, total_tokens: 1234 },
  ai_cost_usd: 0.04,
};

const detail: BotOrchestratorDetail = {
  id: 'o1',
  label: 'Core rotation',
  status: 'active',
  capital: 10000,
  free_capital: 4000,
  allocated_capital: 6000,
  value: 10250,
  total_return_pct: 0.025,
  max_parallel_bots: 3,
  max_bot_share: 0.5,
  max_tickers_per_bot: 5,
  cadence: 'daily',
  model: 'gpt-6-luna',
  benchmark: 'SP500',
  active_bots: 2,
  liquidating_bots: 1,
  created_at: '2026-11-09T14:00:00Z',
  stopped_at: null,
  archived_at: null,
  last_run: partialRun,
  ai_cost_usd: 0.42,
  bots: [
    {
      id: 'b1',
      label: null,
      preset_key: 'rsi_mean_reversion_algo16',
      preset_name: 'RSI Mean Reversion (Algo 16)',
      display_name: 'RSI Mean Reversion (Algo 16) · 2 symbols',
      strategy_key: 'rsi_mean_reversion',
      tickers: ['AAPL', 'NVDA'],
      status: 'active',
      stop_reason: null,
      initial_capital: 3500,
      current_value: 3620,
      total_return_pct: 0.0343,
      open_positions: 1,
      created_at: '2026-11-09T14:00:00Z',
      stopped_at: null,
      capital_returned_at: null,
    },
    {
      id: 'b0',
      label: null,
      preset_key: 'ma_crossover_algo6',
      preset_name: 'MA Crossover (Algo 6)',
      display_name: 'MA Crossover (Algo 6) · XOM',
      strategy_key: 'ma_crossover',
      tickers: ['XOM'],
      status: 'stopped',
      stop_reason: 'orchestrator',
      initial_capital: 2500,
      current_value: 2400,
      total_return_pct: -0.04,
      open_positions: 1,
      created_at: '2026-11-05T14:00:00Z',
      stopped_at: '2026-11-10T14:00:30Z',
      capital_returned_at: null,
    },
  ],
};

function routeGet(overrides: Partial<BotOrchestratorDetail> = {}) {
  return (url: string) => {
    if (url.endsWith('/runs'))
      return Promise.resolve({ data: { items: [partialRun], total: 1 } });
    return Promise.resolve({ data: { ...detail, ...overrides } });
  };
}

function renderDetail() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/orchestrators/o1']}>
        <Routes>
          <Route path="/orchestrators/:id" element={<OrchestratorDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('OrchestratorDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the capital tiles and its bots', async () => {
    mockedGet.mockImplementation(routeGet());
    renderDetail();

    expect(
      await screen.findByRole('heading', { name: 'Core rotation' }),
    ).toBeInTheDocument();
    expect(screen.getByText('$10,250.00')).toBeInTheDocument();
    expect(screen.getByText('+2.50%')).toBeInTheDocument();
    expect(screen.getByText('$4,000.00')).toBeInTheDocument();
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    expect(screen.getByText('1 being sold')).toBeInTheDocument();

    const rsi = screen.getByRole('link', {
      name: 'RSI Mean Reversion (Algo 16) · 2 symbols',
    });
    expect(rsi).toHaveAttribute('href', '/bots/b1');
    const rsiRow = rsi.closest('tr') as HTMLElement;
    expect(within(rsiRow).getByText('AAPL, NVDA')).toBeInTheDocument();
    expect(within(rsiRow).getByText('Active')).toBeInTheDocument();
    const stoppedRow = screen
      .getByRole('link', { name: 'MA Crossover (Algo 6) · XOM' })
      .closest('tr') as HTMLElement;
    expect(within(stoppedRow).getByText('Selling')).toBeInTheDocument();
  });

  it("shows a partial run's market summary, applied and rejected actions", async () => {
    mockedGet.mockImplementation(routeGet());
    const user = userEvent.setup();
    renderDetail();

    await screen.findByText('1 applied · 1 rejected');
    await user.click(screen.getByRole('button', { name: 'Show details' }));

    expect(screen.getByText(/Tech breadth is improving/)).toBeInTheDocument();
    expect(
      screen.getByText(/Deploy donchian_turtle_algo25 on MSFT with \$2,500\.00/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Rejected: Deploy ma_crossover_algo6 on XOM/),
    ).toHaveTextContent('exceeds the free capital');
  });

  it('starts a manual run and shows it as in progress', async () => {
    let queued = false;
    mockedGet.mockImplementation((url: string) =>
      routeGet(
        queued ? { last_run: { ...partialRun, id: 'r2', status: 'queued' } } : {},
      )(url),
    );
    mockedPost.mockImplementation(() => {
      queued = true;
      return Promise.resolve({ data: { ...partialRun, id: 'r2', status: 'queued' } });
    });
    const user = userEvent.setup();
    renderDetail();

    await user.click(await screen.findByRole('button', { name: 'Run now' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/api/v1/bot-orchestrators/o1/runs');
    });
    expect(
      await screen.findByRole('button', { name: 'Run in progress…' }),
    ).toBeDisabled();
    expect(screen.getByText(/A decision run is queued/)).toBeInTheDocument();
  });

  it('asks for confirmation before stopping', async () => {
    mockedGet.mockImplementation(routeGet());
    mockedPost.mockResolvedValue({ data: { ...detail, status: 'stopped' } });
    const user = userEvent.setup();
    renderDetail();

    await user.click(await screen.findByRole('button', { name: 'Stop' }));
    expect(mockedPost).not.toHaveBeenCalled();
    expect(screen.getByText('Stop it and sell all its bots?')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Confirm stop' }));
    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/api/v1/bot-orchestrators/o1/stop');
    });
  });

  it('offers Archive only when stopped', async () => {
    mockedGet.mockImplementation(routeGet());
    const { unmount } = renderDetail();
    await screen.findByRole('heading', { name: 'Core rotation' });
    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument();
    unmount();

    mockedGet.mockImplementation(routeGet({ status: 'stopped' }));
    renderDetail();
    expect(await screen.findByRole('button', { name: 'Archive' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Run now' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
  });

  it('shows the AI cost tile and per-run tokens and cost', async () => {
    mockedGet.mockImplementation(routeGet());
    renderDetail();

    const tile = (await screen.findByText('AI cost')).parentElement!
      .parentElement as HTMLElement;
    expect(within(tile).getByText('$0.42')).toBeInTheDocument();
    expect(await screen.findByTestId('run-usage')).toHaveTextContent(
      '1,234 tokens · $0.04',
    );
  });

  it('renders unavailable cost as an em dash and omits tokens without usage', async () => {
    const run = { ...partialRun, usage: null, ai_cost_usd: null };
    mockedGet.mockImplementation((url: string) =>
      url.endsWith('/runs')
        ? Promise.resolve({ data: { items: [run], total: 1 } })
        : Promise.resolve({ data: { ...detail, ai_cost_usd: null, last_run: run } }),
    );
    renderDetail();

    const tile = (await screen.findByText('AI cost')).parentElement!
      .parentElement as HTMLElement;
    expect(within(tile).getByText('—')).toBeInTheDocument();
    expect(within(tile).getByText('Cost tracking unavailable')).toBeInTheDocument();
    const usage = await screen.findByTestId('run-usage');
    expect(usage).toHaveTextContent('—');
    expect(usage).not.toHaveTextContent('tokens');
  });
});
