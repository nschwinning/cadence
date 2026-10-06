import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import { PaperTradingSessionPage } from './PaperTradingSessionPage';
import { apiClient } from '../../api/client';
import { aiPortfolioKeys } from '../../api/aiPortfolio';
import type {
  AIEventStatus,
  AIPortfolioEvent,
  PaperTrade,
  PaperTradingSession,
  PaperTradingSessionKpis,
} from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);
const mockedPut = vi.mocked(apiClient.put);

const session: PaperTradingSession = {
  id: 's1',
  portfolio_id: 'p1',
  portfolio_name: 'Aggressive Jolly Wozniak',
  strategy_key: 'ai-momentum',
  status: 'active',
  allocated_capital: 100000,
  contributed_capital: 100000,
  max_allocation_pct: 0.25,
  created_at: '2026-09-10T00:00:00Z',
  updated_at: '2026-09-12T00:00:00Z',
  last_run_at: '2026-09-12T09:30:00Z',
  total_trades: 3,
  total_pnl: 500,
  session_metadata: null,
  schedule_mode: 'DAILY_REBALANCING',
  archived_at: null,
  rebalance_prompt_version: 1,
  benchmark: 'SP500',
  asset_types: 'both',
  use_technical_indicators: false,
  stop_loss_enabled: false,
  stop_loss_pct: null,
  risk_guardrails_enabled: false,
  max_asset_class_pct: null,
  min_positions: null,
  max_invested_pct: null,
};

function makeEvent(
  status: AIEventStatus,
  result_payload: AIPortfolioEvent['result_payload'] = null,
): AIPortfolioEvent {
  return {
    id: 'evt-1',
    session_id: 's1',
    portfolio_id: 'p1',
    event_type: 'rebalance',
    status,
    request_payload: null,
    result_payload,
    actions_taken: null,
    research: null,
    trend_context: null,
    error: null,
    duration_ms: null,
    created_at: '2026-09-14T00:00:00Z',
    updated_at: '2026-09-14T00:00:00Z',
  };
}

const REBALANCE_RESULT = {
  evaluation_summary: 'Rotated toward higher-conviction names.',
  portfolio_health: 'Healthy and well diversified.',
  target_allocations: [
    {
      ticker: 'AAPL',
      company_name: 'Apple Inc.',
      allocation_pct: 0.6,
      investment_thesis: 'Durable franchise.',
      confidence: 0.9,
    },
    {
      ticker: 'MSFT',
      company_name: 'Microsoft Corp.',
      allocation_pct: 0.4,
      investment_thesis: 'Cloud growth.',
      confidence: 0.85,
    },
  ],
};

const KPIS: PaperTradingSessionKpis = {
  current_value: 102500,
  unallocated_cash: 20500,
  realised_pnl: 750,
  unrealised_pnl: -200,
  total_fees: 12,
  daily_avg_transaction_cost: 4,
  total_return: 2500,
  total_return_pct: 0.025,
  sharpe_ratio: null,
  benchmark: 'SP500',
  benchmark_return_pct: 0.015,
  excess_return_pct: 0.01,
  excess_return: 1000,
  max_drawdown: 0.1234,
  win_rate: 0.6,
  average_win: 320,
  average_loss: -110,
  best_trade: 900,
  worst_trade: -450,
};

/** A session with no snapshots or closed positions: the new metrics are null. */
const KPIS_NO_RISK_DATA: PaperTradingSessionKpis = {
  ...KPIS,
  sharpe_ratio: 1.234,
  max_drawdown: null,
  win_rate: null,
  average_win: null,
  average_loss: null,
  best_trade: null,
  worst_trade: null,
};

/** Route the mocked GETs by URL to the right fixture. */
function installGet(
  eventStatus: () => AIEventStatus,
  kpis: PaperTradingSessionKpis = KPIS,
) {
  mockedGet.mockImplementation((url: string) => {
    if (url.endsWith('/paper-trading/sessions')) {
      return Promise.resolve({ data: { items: [session], total: 1 } });
    }
    if (url.endsWith('/kpis')) {
      return Promise.resolve({ data: kpis });
    }
    if (url.endsWith('/sector-performance')) {
      return Promise.resolve({ data: { by_sector: [], by_category: [] } });
    }
    if (url.endsWith('/paper-trading/benchmarks')) {
      return Promise.resolve({
        data: [
          { id: 'SP500', name: 'S&P 500' },
          { id: 'DJIA', name: 'Dow Jones Industrial Average' },
        ],
      });
    }
    if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
      return Promise.resolve({ data: { items: [], total: 0 } });
    }
    if (url.includes('/build/status/')) {
      const status = eventStatus();
      return Promise.resolve({
        data: makeEvent(
          status,
          status === 'succeeded' ? REBALANCE_RESULT : null,
        ),
      });
    }
    // trades / runs / positions
    return Promise.resolve({ data: { items: [], total: 0 } });
  });
}

function renderPage(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/paper-trading/s1']}>
        <Routes>
          <Route path="/paper-trading/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...utils, queryClient };
}

describe('PaperTradingSessionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the session header and all resource panels', async () => {
    installGet(() => 'running');

    renderPage(<PaperTradingSessionPage />);

    expect(
      await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' }),
    ).toBeInTheDocument();
    // The strategy is shown as secondary context, not the heading.
    expect(screen.getByText('ai-momentum')).toBeInTheDocument();
    // The rebalance + close actions sit in the header's upper-right corner.
    expect(
      screen.getByRole('button', { name: 'Rebalance now' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Close portfolio' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'AI events' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Trades' })).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Closed positions' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Runs' })).toBeInTheDocument();
  });

  it('falls back to the strategy label when the portfolio name is missing', async () => {
    const unnamed: PaperTradingSession = { ...session, portfolio_name: null };
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [unnamed], total: 1 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        return Promise.resolve({ data: { by_sector: [], by_category: [] } });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        return Promise.resolve({ data: { items: [], total: 0 } });
      }
      if (url.includes('/build/status/')) {
        return Promise.resolve({ data: makeEvent('running') });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });

    renderPage(<PaperTradingSessionPage />);

    expect(
      await screen.findByRole('heading', { name: 'ai-momentum' }),
    ).toBeInTheDocument();
  });

  it('renders the KPI tiles, colours P&L by sign, and shows the Sharpe fallback', async () => {
    installGet(() => 'running');

    renderPage(<PaperTradingSessionPage />);

    // Current value tile.
    expect(await screen.findByText('$102,500.00')).toBeInTheDocument();
    // Unallocated-cash tile shows the session's uninvested cash.
    expect(screen.getByText('Unallocated cash')).toBeInTheDocument();
    expect(screen.getByText('$20,500.00')).toBeInTheDocument();
    // Realised P&L is positive -> green.
    const realised = screen.getByText('$750.00');
    expect(realised).toHaveClass('text-emerald-700');
    // Unrealised P&L is negative -> red.
    const unrealised = screen.getByText('-$200.00');
    expect(unrealised).toHaveClass('text-red-700');
    // Total return leads with the percentage; the money amount is the hint.
    expect(screen.getByText('2.50%')).toHaveClass('text-emerald-700');
    expect(screen.getByText('$2,500.00')).toHaveClass('text-emerald-700');
    // Transaction fees tile shows the cumulative cost.
    expect(screen.getByText('Transaction fees')).toBeInTheDocument();
    expect(screen.getByText('$12.00')).toBeInTheDocument();
    // Daily average transaction cost tile shows the per-snapshot-day figure.
    expect(screen.getByText('Daily avg. transaction cost')).toBeInTheDocument();
    expect(screen.getByText('$4.00')).toBeInTheDocument();
    expect(screen.getByText('Fees per snapshot day')).toBeInTheDocument();
    // Sharpe is null -> fallback copy.
    expect(screen.getByText('Not yet available')).toBeInTheDocument();
  });

  it('shows the daily avg. transaction cost fallback until a snapshot exists', async () => {
    // Sharpe present so the only "Not yet available" copy comes from the daily tile.
    installGet(() => 'running', {
      ...KPIS,
      sharpe_ratio: 1.234,
      daily_avg_transaction_cost: null,
    });

    renderPage(<PaperTradingSessionPage />);

    expect(
      await screen.findByText('Daily avg. transaction cost'),
    ).toBeInTheDocument();
    expect(screen.getByText('Not yet available')).toBeInTheDocument();
    expect(screen.getByText('Needs a snapshot day')).toBeInTheDocument();
  });

  it('shows the computed Sharpe ratio when available', async () => {
    installGet(() => 'running', { ...KPIS, sharpe_ratio: 1.234 });

    renderPage(<PaperTradingSessionPage />);

    expect(await screen.findByText('1.23')).toBeInTheDocument();
    expect(screen.queryByText('Not yet available')).not.toBeInTheDocument();
  });

  it('renders the benchmark-return and excess-return tiles with their values', async () => {
    // Sharpe present so the only "Not yet available" copy would come from the
    // benchmark tiles — of which there is none when both figures are set.
    installGet(() => 'running', { ...KPIS, sharpe_ratio: 1.234 });

    renderPage(<PaperTradingSessionPage />);

    // Both benchmark tiles carry the session's benchmark name in their hints.
    expect(await screen.findByText('Benchmark return')).toBeInTheDocument();
    expect(screen.getByText('Excess return')).toBeInTheDocument();
    // benchmark_return_pct 0.015 -> 1.50%; excess_return_pct 0.01 -> 1.00%.
    expect(screen.getByText('1.50%')).toBeInTheDocument();
    expect(screen.getByText('1.00%')).toBeInTheDocument();
    // The catalog display name resolves the SP500 id in the tile hints.
    expect(screen.getByText('S&P 500, buy & hold')).toBeInTheDocument();
    expect(screen.getByText('vs S&P 500')).toBeInTheDocument();
    // Excess return also shows the monetary excess (net of fees) in its hint.
    expect(screen.getByText('$1,000.00')).toHaveClass('text-emerald-700');
    // With every figure available, no tile shows the unavailable fallback.
    expect(screen.queryByText('Not yet available')).not.toBeInTheDocument();
  });

  it('shows the unavailable state on the benchmark tiles until prices exist', async () => {
    installGet(() => 'running', {
      ...KPIS,
      sharpe_ratio: 1.234,
      benchmark_return_pct: null,
      excess_return_pct: null,
    });

    renderPage(<PaperTradingSessionPage />);

    await screen.findByText('Benchmark return');
    // Both the benchmark-return and excess-return tiles fall back to the copy.
    expect(screen.getAllByText('Not yet available')).toHaveLength(2);
  });

  it('renders the risk & trade-quality group with the new tiles', async () => {
    installGet(() => 'running');

    renderPage(<PaperTradingSessionPage />);

    // Both KPI groups are labelled headings.
    expect(
      await screen.findByRole('heading', { name: 'Performance' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Risk & trade quality' }),
    ).toBeInTheDocument();
    // Max drawdown shows an explicit minus and is coloured as a decline.
    const drawdown = screen.getByText(/12\.34%/);
    expect(drawdown).toHaveClass('text-red-700');
    expect(drawdown.textContent).toContain('−');
    // Win rate is a neutral ratio (no P&L colour).
    expect(screen.getByText('60.00%')).toBeInTheDocument();
    // Average win / best trade are gains (green); average loss / worst trade are
    // signed losses (red).
    expect(screen.getByText('$320.00')).toHaveClass('text-emerald-700');
    expect(screen.getByText('$900.00')).toHaveClass('text-emerald-700');
    expect(screen.getByText('-$110.00')).toHaveClass('text-red-700');
    expect(screen.getByText('-$450.00')).toHaveClass('text-red-700');
  });

  it('shows placeholders for the risk metrics when their inputs are absent', async () => {
    installGet(() => 'running', KPIS_NO_RISK_DATA);

    renderPage(<PaperTradingSessionPage />);

    await screen.findByRole('heading', { name: 'Risk & trade quality' });
    // All six new tiles fall back (Sharpe and the benchmark tiles are populated).
    expect(screen.getAllByText('Not yet available')).toHaveLength(6);
    // Each placeholder explains why via its hint.
    expect(screen.getByText('Needs a value snapshot')).toBeInTheDocument();
    expect(screen.getByText('No winning positions yet')).toBeInTheDocument();
    expect(screen.getByText('No losing positions yet')).toBeInTheDocument();
  });

  it('switches the benchmark and reflects the new selection', async () => {
    installGet(() => 'running');
    mockedPut.mockResolvedValue({ data: { ...session, benchmark: 'DJIA' } });
    const user = userEvent.setup();

    renderPage(<PaperTradingSessionPage />);

    // The switcher preselects the session's current benchmark (SP500).
    const select = await screen.findByLabelText('Benchmark');
    expect(select).toHaveValue('SP500');

    // Choosing another catalog benchmark PUTs the change to the endpoint.
    await user.selectOptions(select, 'DJIA');

    expect(mockedPut).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/benchmark',
      { benchmark: 'DJIA' },
    );
  });

  it('adds capital: a positive amount POSTs to the capital endpoint', async () => {
    installGet(() => 'running');
    mockedPost.mockResolvedValue({
      data: {
        ...session,
        allocated_capital: 105000,
        contributed_capital: 105000,
      },
    });
    const user = userEvent.setup();

    renderPage(<PaperTradingSessionPage />);

    const input = await screen.findByLabelText('Add capital');
    await user.type(input, '5000');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/capital',
      { amount: 5000 },
    );
  });

  it('does not POST for an empty, zero, or negative capital amount', async () => {
    installGet(() => 'running');
    const user = userEvent.setup();

    renderPage(<PaperTradingSessionPage />);

    const input = await screen.findByLabelText('Add capital');
    const button = screen.getByRole('button', { name: 'Add' });

    // Empty: the button is disabled and clicking does nothing.
    expect(button).toBeDisabled();

    // Zero and negative amounts are rejected client-side (no request).
    await user.type(input, '0');
    expect(button).toBeDisabled();
    await user.clear(input);
    await user.type(input, '-100');
    expect(button).toBeDisabled();

    // The order-sync hook may POST to /reconcile on mount, but nothing ever hits
    // the capital endpoint.
    expect(mockedPost).not.toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/capital',
      expect.anything(),
    );
  });

  it('surfaces an error when the capital increase request fails', async () => {
    installGet(() => 'running');
    mockedPost.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();

    renderPage(<PaperTradingSessionPage />);

    const input = await screen.findByLabelText('Add capital');
    await user.type(input, '5000');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(
      await screen.findByText('Could not add capital.'),
    ).toBeInTheDocument();
  });

  it('triggers a rebalance and reflects terminal feedback without manual refresh', async () => {
    let status: AIEventStatus = 'running';
    installGet(() => status);
    mockedPost.mockResolvedValue({
      data: { event_id: 'evt-1', status: 'queued', started: true },
    });
    const user = userEvent.setup();

    const { queryClient } = renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    await user.click(screen.getByRole('button', { name: 'Rebalance now' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/ai-portfolio/sessions/s1/rebalance',
      {},
    );
    expect(await screen.findByText(/Rebalance in progress/i)).toBeInTheDocument();

    // Advance the event to terminal; force the poll refetch (jsdom).
    status = 'succeeded';
    await queryClient.refetchQueries({
      queryKey: aiPortfolioKeys.buildStatus('evt-1'),
    });

    expect(
      await screen.findByText('Rebalance succeeded'),
    ).toBeInTheDocument();

    // The new rebalance payload (summary, health, target weights) is rendered.
    expect(
      screen.getByText('Rotated toward higher-conviction names.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Healthy and well diversified/)).toBeInTheDocument();
    expect(screen.getByText('Target allocations')).toBeInTheDocument();
    expect(screen.getByText('60.0%')).toBeInTheDocument();
    expect(screen.getByText('40.0%')).toBeInTheDocument();
  });

  it('shows the frozen rebalance-prompt version', async () => {
    installGet(() => 'running');

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    expect(screen.getByText('Prompt version')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
  });

  it('shows no archive control for an active session', async () => {
    installGet(() => 'running');

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    expect(
      screen.queryByRole('button', { name: 'Archive' }),
    ).not.toBeInTheDocument();
  });

  it('archives a stopped session from the header control', async () => {
    const stopped: PaperTradingSession = { ...session, status: 'stopped' };
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [stopped], total: 1 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        return Promise.resolve({ data: { by_sector: [], by_category: [] } });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        return Promise.resolve({ data: { items: [], total: 0 } });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });
    mockedPost.mockResolvedValue({
      data: { ...stopped, archived_at: '2026-09-16T00:00:00Z' },
    });
    const user = userEvent.setup();

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    await user.click(screen.getByRole('button', { name: 'Archive' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/archive',
      {},
    );
  });

  it('shows an Unarchive control for an archived session', async () => {
    const archived: PaperTradingSession = {
      ...session,
      status: 'stopped',
      archived_at: '2026-09-16T00:00:00Z',
    };
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [archived], total: 1 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        return Promise.resolve({ data: { by_sector: [], by_category: [] } });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        return Promise.resolve({ data: { items: [], total: 0 } });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    expect(
      screen.getByRole('button', { name: 'Unarchive' }),
    ).toBeInTheDocument();
  });

  it('reconciles the session orders when the page opens', async () => {
    installGet(() => 'running');
    mockedPost.mockResolvedValue({
      data: {
        trades_seen: 0,
        trades_reconciled: 0,
        trades_filled: 0,
        trades_basis_corrected: 0,
        trades: [],
      },
    });

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/reconcile',
      {},
    );
  });

  it('shows the stop-loss configuration when the session opted in', async () => {
    const withStopLoss: PaperTradingSession = {
      ...session,
      stop_loss_enabled: true,
      stop_loss_pct: 0.15,
    };
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [withStopLoss], total: 1 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        return Promise.resolve({ data: { by_sector: [], by_category: [] } });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        return Promise.resolve({ data: { items: [], total: 0 } });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    expect(screen.getByText('Stop-loss')).toBeInTheDocument();
    expect(screen.getByText('15% below avg cost')).toBeInTheDocument();
  });

  it('shows the stop-loss config as Off when the session did not opt in', async () => {
    installGet(() => 'running');

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    expect(screen.getByText('Stop-loss')).toBeInTheDocument();
    // Both the Stop-loss and Risk-guardrails tiles read "Off" by default.
    expect(screen.getAllByText('Off')).toHaveLength(2);
  });

  it('shows the risk-guardrail configuration when the session opted in', async () => {
    const withGuardrails: PaperTradingSession = {
      ...session,
      risk_guardrails_enabled: true,
      max_allocation_pct: 0.25,
      max_asset_class_pct: 0.6,
      min_positions: 5,
      max_invested_pct: 0.95,
    };
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [withGuardrails], total: 1 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        return Promise.resolve({ data: { by_sector: [], by_category: [] } });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        return Promise.resolve({ data: { items: [], total: 0 } });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    expect(screen.getByText('Risk guardrails')).toBeInTheDocument();
    expect(screen.getByText('Max/asset: 25%')).toBeInTheDocument();
    expect(screen.getByText('Max/class: 60%')).toBeInTheDocument();
    expect(screen.getByText('Min positions: 5')).toBeInTheDocument();
    expect(screen.getByText('Max invested: 95%')).toBeInTheDocument();
  });

  it('shows the risk-guardrail config as Off when the session did not opt in', async () => {
    installGet(() => 'running');

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    expect(screen.getByText('Risk guardrails')).toBeInTheDocument();
    // Both Stop-loss and Risk guardrails read "Off" for the default session.
    expect(screen.getAllByText('Off')).toHaveLength(2);
  });

  it('badges stop-loss trades and runs as stop-loss activity', async () => {
    const stopTrade: PaperTrade = {
      id: 'trade-sl',
      session_id: 's1',
      ai_portfolio_event_id: null,
      ticker: 'AAPL',
      side: 'sell',
      quantity: 10,
      price: 100,
      notional: 1000,
      signal_type: 'stop_loss',
      executed_at: '2026-09-12T09:30:00Z',
      order_id: 'ord-sl',
      order_status: 'filled',
      filled_price: 100,
      filled_at: '2026-09-12T09:30:01Z',
    };
    const stopRun = {
      id: 'run-sl',
      session_id: 's1',
      ai_portfolio_event_id: null,
      run_at: '2026-09-12T09:30:00Z',
      run_trigger: 'stop_loss',
      status: 'completed',
      signals_scanned: 1,
      signals_actionable: 1,
      orders_executed: 1,
      orders_skipped: 0,
      duration_ms: 42,
    };
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [session], total: 1 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        return Promise.resolve({ data: { by_sector: [], by_category: [] } });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        return Promise.resolve({ data: { items: [], total: 0 } });
      }
      if (url.includes('/trades')) {
        return Promise.resolve({ data: { items: [stopTrade], total: 1 } });
      }
      if (url.includes('/runs')) {
        return Promise.resolve({ data: { items: [stopRun], total: 1 } });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    // Both the stop-loss trade and run render the distinct amber "Stop-loss"
    // badge (the header also has a "Stop-loss" config label, so filter by the
    // badge styling to count only the activity badges).
    const badges = (await screen.findAllByText('Stop-loss')).filter((el) =>
      el.className.includes('bg-amber-100'),
    );
    expect(badges).toHaveLength(2);
  });

  it('links AI-driven runs to their detail page and leaves non-AI runs plain', async () => {
    const aiRun = {
      id: 'run-ai',
      session_id: 's1',
      ai_portfolio_event_id: 'evt-9',
      run_at: '2026-09-12T09:30:00Z',
      run_trigger: 'ai_rebalance',
      status: 'completed',
      signals_scanned: 4,
      signals_actionable: 2,
      orders_executed: 2,
      orders_skipped: 0,
      duration_ms: 88,
    };
    const scanRun = {
      id: 'run-scan',
      session_id: 's1',
      ai_portfolio_event_id: null,
      run_at: '2026-09-11T09:30:00Z',
      run_trigger: 'scheduled',
      status: 'completed',
      signals_scanned: 1,
      signals_actionable: 0,
      orders_executed: 0,
      orders_skipped: 0,
      duration_ms: 12,
    };
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [session], total: 1 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        return Promise.resolve({ data: { by_sector: [], by_category: [] } });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        return Promise.resolve({ data: { items: [], total: 0 } });
      }
      if (url.includes('/runs')) {
        return Promise.resolve({ data: { items: [aiRun, scanRun], total: 2 } });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });

    renderPage(<PaperTradingSessionPage />);
    // Wait for the run rows to render (the AI run's duration is unique) before
    // asserting on links, so we don't race the runs query.
    await screen.findByText('88 ms');

    // The AI run's timestamp cell links to its run detail; the scheduled run has
    // no producing AI event, so exactly one run links to /runs/.
    const runLinks = screen
      .getAllByRole('link')
      .filter((el) => el.getAttribute('href')?.startsWith('/runs/'));
    expect(runLinks).toHaveLength(1);
    expect(runLinks[0]).toHaveAttribute('href', '/runs/evt-9');
  });

  it('shows the AI events server total, not just the current page length', async () => {
    const oneEvent = makeEvent('succeeded');
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [session], total: 1 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        return Promise.resolve({ data: { by_sector: [], by_category: [] } });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        // One row on this page, but twelve across all pages.
        return Promise.resolve({ data: { items: [oneEvent], total: 12 } });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });

    renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'Aggressive Jolly Wozniak' });

    // The panel header and pagination summary both reflect the server total (12),
    // even though the current page holds a single event (page size 5 -> 3 pages).
    expect(await screen.findByText('12 total')).toBeInTheDocument();
    expect(screen.getByText('Showing 1–5 of 12 events')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
  });

  it('requests the next page offset when browsing the trades table', async () => {
    const tradeRows = Array.from({ length: 10 }, (_, i) => ({
      id: `trade-${i}`,
      session_id: 's1',
      ai_portfolio_event_id: null,
      ticker: 'AAPL',
      side: 'buy',
      quantity: 1,
      price: 100,
      notional: 100,
      signal_type: 'entry',
      executed_at: '2026-09-12T09:30:00Z',
      order_id: `ord-${i}`,
      order_status: 'filled',
      filled_price: 100,
      filled_at: '2026-09-12T09:30:01Z',
    }));
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [session], total: 1 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        return Promise.resolve({ data: { by_sector: [], by_category: [] } });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        return Promise.resolve({ data: { items: [], total: 0 } });
      }
      if (url.includes('/trades')) {
        return Promise.resolve({ data: { items: tradeRows, total: 25 } });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });
    mockedPost.mockResolvedValue({
      data: {
        trades_seen: 0,
        trades_reconciled: 0,
        trades_filled: 0,
        trades_basis_corrected: 0,
        trades: [],
      },
    });
    const user = userEvent.setup();

    renderPage(<PaperTradingSessionPage />);
    // Wait until the trades page has loaded (empty panels render no pagination).
    await screen.findByText('Showing 1–10 of 25 trades');

    // The trades panel is the only one with data, so its Next control is the
    // sole one on the page.
    const nextButtons = screen
      .getAllByRole('button', { name: 'Next page' })
      .filter((b) => !(b as HTMLButtonElement).disabled);
    expect(nextButtons).toHaveLength(1);

    await user.click(nextButtons[0]);

    // Page 2 requests offset = pageSize (10) with the fixed trades page size.
    expect(mockedGet).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/trades',
      { params: { limit: 10, offset: 10 } },
    );
  });

  it('renders a fractional crypto trade quantity trimmed of trailing zeros', async () => {
    const cryptoTrade: PaperTrade = {
      id: 'trade-1',
      session_id: 's1',
      ai_portfolio_event_id: null,
      ticker: 'BTCUSD',
      side: 'buy',
      quantity: 0.05123456,
      price: 60000,
      notional: 3074.07,
      signal_type: 'entry',
      executed_at: '2026-09-12T09:30:00Z',
      order_id: 'ord-1',
      order_status: 'filled',
      filled_price: 60000,
      filled_at: '2026-09-12T09:30:01Z',
    };
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [session], total: 1 } });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        return Promise.resolve({ data: { items: [], total: 0 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        return Promise.resolve({ data: { by_sector: [], by_category: [] } });
      }
      if (url.includes('/trades')) {
        return Promise.resolve({ data: { items: [cryptoTrade], total: 1 } });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });

    renderPage(<PaperTradingSessionPage />);

    // Fractional crypto quantity shows its fraction (capped at 6 digits)...
    expect(await screen.findByText('0.051235')).toBeInTheDocument();
    // ...and a whole-share equity would not render padded zeros.
    expect(screen.queryByText('0.051235')?.textContent).not.toContain('000');
  });

  /** Build a by-category attribution group (defaults make it a currently-held row). */
  function categoryGroup(key: string, marketValue = 5000) {
    return {
      key,
      market_value: marketValue,
      realized_pnl: 0,
      unrealized_pnl: 0,
      total_pnl: 0,
      return_pct: null,
    };
  }

  /** Install GETs for the scope tests, with a chosen session + by-category holdings. */
  function installScopeGet(
    scopeSession: PaperTradingSession,
    byCategory: ReturnType<typeof categoryGroup>[],
  ) {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/paper-trading/sessions')) {
        return Promise.resolve({ data: { items: [scopeSession], total: 1 } });
      }
      if (url.endsWith('/kpis')) {
        return Promise.resolve({ data: KPIS });
      }
      if (url.endsWith('/sector-performance')) {
        // A sentinel sector row (the card's default grouping) renders once the
        // attribution loads, giving the scope tests a deterministic wait anchor.
        return Promise.resolve({
          data: { by_sector: [categoryGroup('Technology')], by_category: byCategory },
        });
      }
      if (url.endsWith('/paper-trading/benchmarks')) {
        return Promise.resolve({ data: [{ id: 'SP500', name: 'S&P 500' }] });
      }
      if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
        return Promise.resolve({ data: { items: [], total: 0 } });
      }
      return Promise.resolve({ data: { items: [], total: 0 } });
    });
  }

  it('shows the current scope and requests a non-liquidating change without a warning', async () => {
    // Stocks-only session holding equity; widening to both liquidates nothing.
    const scoped: PaperTradingSession = { ...session, asset_types: 'stocks' };
    installScopeGet(scoped, [categoryGroup('stock')]);
    mockedPut.mockResolvedValue({ data: { ...scoped, asset_types: 'both' } });
    const user = userEvent.setup();

    renderPage(<PaperTradingSessionPage />);

    // The read-only fact tile and the switcher both reflect the current scope.
    const select = await screen.findByLabelText('Change scope');
    expect(select).toHaveValue('stocks');
    // The "Scope" fact tile is present (its label also appears as a select option).
    expect(screen.getByText('Scope')).toBeInTheDocument();
    expect(screen.getAllByText('Stocks only').length).toBeGreaterThanOrEqual(1);

    await user.selectOptions(select, 'both');

    // A widening never warns: the change is requested immediately.
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(mockedPut).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/scope',
      { asset_types: 'both' },
    );
  });

  it('warns before a liquidating narrowing and only requests the change on confirm', async () => {
    // Both-scope session holding crypto; narrowing to stocks sells the crypto.
    installScopeGet(session, [categoryGroup('crypto')]);
    mockedPut.mockResolvedValue({ data: { ...session, asset_types: 'stocks' } });
    const user = userEvent.setup();

    renderPage(<PaperTradingSessionPage />);
    // Wait for the attribution to load so the held crypto class is known.
    await screen.findByText('Technology');

    const select = await screen.findByLabelText('Change scope');
    await user.selectOptions(select, 'stocks');

    // The narrowing warns and does not request the change yet.
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(mockedPut).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Sell & change' }));

    expect(mockedPut).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/scope',
      { asset_types: 'stocks' },
    );
  });

  it('cancels a liquidating narrowing when the warning is declined', async () => {
    installScopeGet(session, [categoryGroup('crypto')]);
    const user = userEvent.setup();

    renderPage(<PaperTradingSessionPage />);
    await screen.findByText('Technology');

    const select = await screen.findByLabelText('Change scope');
    await user.selectOptions(select, 'stocks');

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    // Declining dismisses the warning, requests nothing, and keeps the scope.
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(mockedPut).not.toHaveBeenCalled();
    expect(select).toHaveValue('both');
  });

  it('requests a non-liquidating narrowing with no warning when nothing held is excluded', async () => {
    // Both-scope session holding only equity; narrowing to stocks excludes nothing.
    installScopeGet(session, [categoryGroup('stock')]);
    mockedPut.mockResolvedValue({ data: { ...session, asset_types: 'stocks' } });
    const user = userEvent.setup();

    renderPage(<PaperTradingSessionPage />);
    // Wait for the attribution to load so held classes are known (equity only).
    await screen.findByText('Technology');

    const select = await screen.findByLabelText('Change scope');
    await user.selectOptions(select, 'stocks');

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(mockedPut).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/scope',
      { asset_types: 'stocks' },
    );
  });
});
