import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import { BotSessionPage } from './BotSessionPage';
import type { AxiosRequestConfig } from 'axios';
import { apiClient } from '../../api/client';
import type {
  BotKpis,
  BotSession,
  BotSessionSummary,
  BotTrade,
} from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

const bot: BotSession = {
  id: 'b1',
  strategy_key: 'ma_crossover',
  label: 'Apple crossover',
  display_name: 'Apple crossover',
  status: 'active',
  benchmark: 'SP500',
  initial_capital: 10000,
  allocated_capital: 10000,
  cash: 500,
  current_value: 10325,
  eod_value: 10250,
  sizing_method: 'atr_risk',
  risk_pct: 0.01,
  atr_period: 14,
  atr_k: 2.0,
  max_position_pct: 0.25,
  max_positions: 10,
  strategy_params: { fast_period: 20, slow_period: 50 },
  take_profit_pct: 0.2,
  stop_loss_pct: null,
  drawdown_stop_pct: 0.25,
  cash_buffer_pct: 0.02,
  peak_value: 10500,
  preset_key: null,
  preset_customized: false,
  origin: 'manual',
  orchestrator_id: null,
  orchestrator_label: null,
  symbols: [
    { asset_id: 1, ticker: 'AAPL', alpaca_symbol: 'AAPL' },
    { asset_id: 2, ticker: 'MSFT', alpaca_symbol: 'MSFT' },
  ],
  positions: [
    {
      asset_id: 1,
      ticker: 'AAPL',
      alpaca_symbol: 'AAPL',
      quantity: 50,
      avg_price: 190,
      opened_at: '2026-10-02T13:35:00Z',
    },
  ],
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
  cash: 737,
  allocated_capital: 10000,
  total_return: 325,
  total_return_pct: 0.0325,
  realised_pnl: 125,
  unrealised_pnl: 200,
  total_fees: 2,
  total_trades: 3,
  max_drawdown: 0.012,
  sharpe_ratio: 1.42,
  best_trade: {
    ticker: 'AAPL',
    realised_pnl: 412,
    quantity: 10,
    entry_price: 180,
    entry_at: '2026-10-02T13:35:00Z',
    exit_price: 221.2,
    exit_at: '2026-10-03T15:00:00Z',
  },
  worst_trade: {
    ticker: 'MSFT',
    realised_pnl: -88,
    quantity: 4,
    entry_price: 420,
    entry_at: '2026-10-02T13:35:00Z',
    exit_price: 398,
    exit_at: '2026-10-04T15:00:00Z',
  },
  benchmark: 'SP500',
  benchmark_return_pct: 0.02,
  excess_return_pct: 0.0125,
  eod_value: 10250,
  value_as_of: '2026-10-05T18:00:00Z',
  value_is_intraday: true,
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

const summary: BotSessionSummary = {
  stats: {
    stop_reason: 'drawdown_kill_switch',
    stopped_at: '2026-10-05T16:00:00Z',
    started_at: '2026-10-01T00:00:00Z',
    lifespan_days: 4,
    final_value: 9800,
    allocated_capital: 10000,
    total_return: -200,
    total_return_pct: -0.02,
    realised_pnl: -200,
    peak_value: 10500,
    max_drawdown: 0.0667,
    trade_count: 2,
    win_rate: 0.5,
    best_trade: {
      ticker: 'AAPL',
      realised_pnl: 120,
      quantity: 10,
      entry_price: 50,
      entry_at: '2026-10-02T09:00:00Z',
      exit_price: 62,
      exit_at: '2026-10-03T09:00:00Z',
    },
    worst_trade: {
      ticker: 'MSFT',
      realised_pnl: -320,
      quantity: 5,
      entry_price: 100,
      entry_at: '2026-10-02T09:00:00Z',
      exit_price: 36,
      exit_at: '2026-10-03T09:00:00Z',
    },
    benchmark: 'SP500',
    benchmark_return_pct: 0.01,
    excess_return_pct: -0.03,
  },
  narrative:
    '**The kill-switch fired.**\n\nThe bot gave back its gains and stopped at its drawdown floor.',
  model: 'gpt-x',
  generated_at: '2026-10-05T16:05:00Z',
};

/** Route every GET the detail page issues by URL suffix. */
function routeGet(
  overrides: {
    session?: BotSession;
    kpis?: BotKpis;
    summary?: BotSessionSummary;
  } = {},
) {
  return (url: string) => {
    if (url.endsWith('/kpis'))
      return Promise.resolve({ data: overrides.kpis ?? kpis });
    if (url.endsWith('/benchmarks'))
      return Promise.resolve({ data: [{ id: 'SP500', name: 'S&P 500' }] });
    if (url.endsWith('/value-history'))
      return Promise.resolve({ data: { items: [], total: 0 } });
    if (url.endsWith('/trades'))
      return Promise.resolve({ data: { items: [trade], total: 1 } });
    if (url.endsWith('/summary'))
      return Promise.resolve({ data: overrides.summary ?? summary });
    if (url.endsWith('/bots/presets'))
      return Promise.resolve({
        data: [
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
        ],
      });
    if (url.endsWith('/bots/strategies'))
      return Promise.resolve({
        data: [
          {
            key: 'ma_crossover',
            display_name: 'Moving-Average Crossover',
            explanation: '',
            required_history: 13,
            params_schema: {},
          },
        ],
      });
    return Promise.resolve({ data: overrides.session ?? bot });
  };
}

/** The tile card wrapping a given label (the label sits in a flex row inside it). */
function tileOf(label: string): HTMLElement {
  return screen.getByText(label).closest('div')!.parentElement as HTMLElement;
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
    // Live and end-of-day value tiles are distinct; the redundant "Allocated
    // capital" tile is gone and the section carries no single freshness badge —
    // each tile instead carries its own live/EOD badge.
    const liveTile = tileOf('Live value');
    expect(within(liveTile).getByText('$10,325.00')).toBeInTheDocument();
    // The fixture's value came from an intraday point, so the live-value tile is
    // badged live; the end-of-day tile is always badged EOD.
    expect(within(liveTile).getByTestId('tile-freshness-live')).toBeInTheDocument();
    const eodTile = tileOf('End of day value');
    expect(within(eodTile).getByText('$10,250.00')).toBeInTheDocument();
    expect(within(eodTile).getByTestId('tile-freshness-eod')).toBeInTheDocument();
    expect(screen.queryByText('Allocated capital')).not.toBeInTheDocument();
    expect(screen.queryByTestId('freshness-live')).not.toBeInTheDocument();
    // Snapshot-derived tiles are badged EOD; current/marked-to-market tiles live.
    expect(
      within(tileOf('Maximum drawdown')).getByTestId('tile-freshness-eod'),
    ).toBeInTheDocument();
    expect(
      within(tileOf('Available cash')).getByTestId('tile-freshness-live'),
    ).toBeInTheDocument();
    expect(screen.getByText('$737.00')).toBeInTheDocument(); // available cash
    expect(screen.getByText('3.25%')).toBeInTheDocument(); // total return pct
    // Best/worst closed round-trip tiles.
    const best = tileOf('Best trade');
    expect(within(best).getByText('$412.00')).toBeInTheDocument();
    expect(within(best).getByText('AAPL')).toBeInTheDocument();
    const worst = tileOf('Worst trade');
    expect(within(worst).getByText('-$88.00')).toBeInTheDocument();
    expect(within(worst).getByText('MSFT')).toBeInTheDocument();
    // Benchmark-comparison tile replaces the (always-$0) transaction-fees tile.
    const benchmarkTile = (
      await screen.findByText('vs S&P 500')
    ).closest('div')!.parentElement as HTMLElement;
    expect(
      within(benchmarkTile).getByTestId('tile-freshness-eod'),
    ).toBeInTheDocument();
    expect(within(benchmarkTile).getByText('1.25%')).toBeInTheDocument(); // excess
    expect(
      within(benchmarkTile).getByText('Benchmark 2.00%, buy & hold'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Transaction fees')).not.toBeInTheDocument();
    // Trade ledger row.
    const row = screen.getByText('fast SMA crossed above slow').closest('tr') as HTMLElement;
    expect(within(row).getByText('buy')).toBeInTheDocument();
    expect(within(row).getByText('filled')).toBeInTheDocument();
  });

  it('badges observation-derived tiles end-of-day when the value is not intraday', async () => {
    mockedGet.mockImplementation(
      routeGet({ kpis: { ...kpis, value_is_intraday: false } }),
    );

    renderDetail(<BotSessionPage />);

    await screen.findByRole('heading', { name: 'Apple crossover' });
    // When the current value came from a daily snapshot, the live-value,
    // total-return and unrealised-P&L tiles are badged EOD, not live.
    expect(
      within(tileOf('Live value')).getByTestId('tile-freshness-eod'),
    ).toBeInTheDocument();
    expect(
      within(tileOf('Total return')).getByTestId('tile-freshness-eod'),
    ).toBeInTheDocument();
    expect(
      within(tileOf('Unrealised P&L')).getByTestId('tile-freshness-eod'),
    ).toBeInTheDocument();
    // Always-live tiles keep their live badge regardless of the value basis.
    expect(
      within(tileOf('Available cash')).getByTestId('tile-freshness-live'),
    ).toBeInTheDocument();
  });

  it('renders the Sharpe ratio tile when a value is present', async () => {
    mockedGet.mockImplementation(routeGet());

    renderDetail(<BotSessionPage />);

    expect(await screen.findByText('Sharpe ratio')).toBeInTheDocument();
    expect(screen.getByText('1.42')).toBeInTheDocument();
    expect(screen.getByText('Annualised, from daily NAV')).toBeInTheDocument();
  });

  it('shows the not-yet-available Sharpe state when the value is null', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/kpis'))
        return Promise.resolve({ data: { ...kpis, sharpe_ratio: null } });
      if (url.endsWith('/value-history'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      if (url.endsWith('/trades'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      return Promise.resolve({ data: bot });
    });

    renderDetail(<BotSessionPage />);

    expect(await screen.findByText('Sharpe ratio')).toBeInTheDocument();
    expect(screen.getByText('Not yet available')).toBeInTheDocument();
    expect(screen.getByText('Needs more daily history')).toBeInTheDocument();
  });

  it('shows a no-closed-trades state when best/worst trade are absent', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/kpis'))
        return Promise.resolve({
          data: { ...kpis, best_trade: null, worst_trade: null },
        });
      if (url.endsWith('/value-history'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      if (url.endsWith('/trades'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      return Promise.resolve({ data: bot });
    });

    renderDetail(<BotSessionPage />);

    expect(await screen.findByText('Best trade')).toBeInTheDocument();
    expect(screen.getByText('Worst trade')).toBeInTheDocument();
    // Both tiles fall back to the empty state.
    expect(screen.getAllByText('No closed trades yet')).toHaveLength(2);
  });

  it('shows the benchmark tile placeholder when the comparison is unavailable', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/kpis'))
        return Promise.resolve({
          data: { ...kpis, benchmark_return_pct: null, excess_return_pct: null },
        });
      if (url.endsWith('/benchmarks'))
        return Promise.resolve({ data: [{ id: 'SP500', name: 'S&P 500' }] });
      if (url.endsWith('/value-history'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      if (url.endsWith('/trades'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      return Promise.resolve({ data: bot });
    });

    renderDetail(<BotSessionPage />);

    const benchmarkTile = (
      await screen.findByText('vs S&P 500')
    ).closest('div')!.parentElement as HTMLElement;
    expect(within(benchmarkTile).getByText('—')).toBeInTheDocument();
    expect(
      within(benchmarkTile).getByText('Needs a daily snapshot'),
    ).toBeInTheDocument();
  });

  it('sorts open positions by ticker by default and by opened timestamp on demand', async () => {
    // Ticker order (AAPL, MSFT) differs from opened order (MSFT earlier) so the
    // two sorts are distinguishable.
    const multi: BotSession = {
      ...bot,
      positions: [
        {
          asset_id: 1,
          ticker: 'AAPL',
          alpaca_symbol: 'AAPL',
          quantity: 50,
          avg_price: 190,
          opened_at: '2026-10-05T13:35:00Z',
        },
        {
          asset_id: 2,
          ticker: 'MSFT',
          alpaca_symbol: 'MSFT',
          quantity: 10,
          avg_price: 300,
          opened_at: '2026-10-02T13:35:00Z',
        },
      ],
    };
    mockedGet.mockImplementation(routeGet({ session: multi }));
    const user = userEvent.setup();

    renderDetail(<BotSessionPage />);

    const table = (await screen.findByText('Avg price')).closest(
      'table',
    ) as HTMLElement;
    const tickerOrder = () =>
      within(table)
        .getAllByRole('link')
        .map((a) => a.textContent);
    // Default: by ticker → AAPL before MSFT.
    expect(tickerOrder()).toEqual(['AAPL', 'MSFT']);

    // Switch to opened-timestamp order → MSFT (opened earlier) first.
    await user.selectOptions(screen.getByLabelText('Sort by'), 'opened');
    expect(tickerOrder()).toEqual(['MSFT', 'AAPL']);
  });

  it('paginates the trade ledger with Previous/Next controls', async () => {
    // 25 trades over a page size of 20 → two pages. Items differ by page so we
    // can tell which page is showing; total drives the "Page X of N" indicator.
    mockedGet.mockImplementation((url: string, config?: AxiosRequestConfig) => {
      if (url.endsWith('/kpis')) return Promise.resolve({ data: kpis });
      if (url.endsWith('/value-history'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      if (url.endsWith('/trades')) {
        const params = config?.params as { offset?: number } | undefined;
        const offset = params?.offset ?? 0;
        const reason = offset === 0 ? 'page-one-trade' : 'page-two-trade';
        return Promise.resolve({
          data: { items: [{ ...trade, id: `t-${offset}`, reason }], total: 25 },
        });
      }
      return Promise.resolve({ data: bot });
    });
    const user = userEvent.setup();

    renderDetail(<BotSessionPage />);

    await screen.findByRole('heading', { name: 'Apple crossover' });
    // Page 1: indicator, Previous disabled, first-page content.
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    expect(await screen.findByText('page-one-trade')).toBeInTheDocument();

    // Advance → offset 20 requested, page 2 content, Next now disabled.
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByText('page-two-trade')).toBeInTheDocument();
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled();
    expect(mockedGet).toHaveBeenCalledWith(
      expect.stringContaining('/trades'),
      expect.objectContaining({ params: expect.objectContaining({ offset: 20 }) }),
    );
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

  it('renders the open positions table for a multi-position bot', async () => {
    const multi: BotSession = {
      ...bot,
      positions: [
        {
          asset_id: 1,
          ticker: 'AAPL',
          alpaca_symbol: 'AAPL',
          quantity: 50,
          avg_price: 190,
          opened_at: '2026-10-02T13:35:00Z',
        },
        {
          asset_id: 2,
          ticker: 'MSFT',
          alpaca_symbol: 'MSFT',
          quantity: 10,
          avg_price: 300,
          opened_at: '2026-10-03T13:35:00Z',
        },
      ],
    };
    mockedGet.mockImplementation(routeGet({ session: multi }));

    renderDetail(<BotSessionPage />);

    await screen.findByRole('heading', { name: 'Open positions' });
    // Scope to the positions table via its distinctive "Avg price" column header
    // (the table body renders only after the session query resolves).
    const table = (await screen.findByText('Avg price')).closest(
      'table',
    ) as HTMLElement;
    expect(within(table).getByText('AAPL')).toBeInTheDocument();
    expect(within(table).getByText('MSFT')).toBeInTheDocument();
    expect(within(table).getByText('$190.00')).toBeInTheDocument();
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

  // Session summary -------------------------------------------------------
  it('hides the session summary for an active bot', async () => {
    mockedGet.mockImplementation(routeGet());

    renderDetail(<BotSessionPage />);

    await screen.findByRole('heading', { name: 'Apple crossover' });
    expect(
      screen.queryByRole('heading', { name: 'Session summary' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('summary-stop-banner'),
    ).not.toBeInTheDocument();
  });

  it('shows the session summary with stats, reason banner and trade detail for a stopped bot', async () => {
    mockedGet.mockImplementation(
      routeGet({ session: { ...bot, status: 'stopped' } }),
    );

    renderDetail(<BotSessionPage />);

    // Stop-reason banner (awaits the summary query resolving).
    const banner = await screen.findByTestId('summary-stop-banner');
    expect(banner).toHaveTextContent('Stopped by the drawdown kill-switch');
    // Stats grid.
    const panel = screen.getByText('Session summary').closest('.rounded-lg') as HTMLElement;
    expect(within(panel).getByText('$9,800.00')).toBeInTheDocument(); // final value
    expect(within(panel).getByText('$10,500.00')).toBeInTheDocument(); // peak value
    expect(within(panel).getByText('4 days')).toBeInTheDocument(); // lifespan
    // Best-trade tile carries the exact entry→exit fills.
    const best = within(panel).getByText('Best trade').closest('div')!
      .parentElement as HTMLElement;
    expect(within(best).getByText('$120.00')).toBeInTheDocument();
    expect(within(best).getByText(/AAPL/)).toBeInTheDocument();
    expect(within(best).getByText(/\$50\.00/)).toBeInTheDocument(); // entry price
    expect(within(best).getByText(/\$62\.00/)).toBeInTheDocument(); // exit price
    // AI narrative rendered.
    expect(screen.getByText('The kill-switch fired.')).toBeInTheDocument();
  });

  it('shows a placeholder when the AI narrative is absent', async () => {
    mockedGet.mockImplementation(
      routeGet({
        session: { ...bot, status: 'stopped' },
        summary: { ...summary, narrative: null, generated_at: null },
      }),
    );

    renderDetail(<BotSessionPage />);

    expect(
      await screen.findByTestId('summary-narrative-placeholder'),
    ).toBeInTheDocument();
  });

  it('shows a loading state while the summary generates', async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith('/kpis')) return Promise.resolve({ data: kpis });
      if (url.endsWith('/benchmarks'))
        return Promise.resolve({ data: [{ id: 'SP500', name: 'S&P 500' }] });
      if (url.endsWith('/value-history'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      if (url.endsWith('/trades'))
        return Promise.resolve({ data: { items: [], total: 0 } });
      // The summary never resolves → the panel stays in its loading state.
      if (url.endsWith('/summary')) return new Promise(() => {});
      return Promise.resolve({ data: { ...bot, status: 'stopped' } });
    });

    renderDetail(<BotSessionPage />);

    const panel = (
      await screen.findByText('Session summary')
    ).closest('.rounded-lg') as HTMLElement;
    expect(within(panel).getByRole('status')).toHaveTextContent('Loading…');
  });
  it('shows "Custom configuration" for a session created without a preset', async () => {
    mockedGet.mockImplementation(routeGet());
    renderDetail(<BotSessionPage />);

    const fact = (await screen.findByText('Preset')).parentElement as HTMLElement;
    expect(within(fact).getByText('Custom configuration')).toBeInTheDocument();
  });

  it('shows the preset name without a customized mark for an unchanged preset', async () => {
    mockedGet.mockImplementation(
      routeGet({ session: { ...bot, preset_key: 'ma_crossover_algo6' } }),
    );
    renderDetail(<BotSessionPage />);

    const fact = (await screen.findByText('Preset')).parentElement as HTMLElement;
    expect(await within(fact).findByText('MA Crossover (Algo 6)')).toBeInTheDocument();
    expect(within(fact).queryByText('Customized')).not.toBeInTheDocument();
  });

  it('marks a customized preset session', async () => {
    mockedGet.mockImplementation(
      routeGet({
        session: { ...bot, preset_key: 'ma_crossover_algo6', preset_customized: true },
      }),
    );
    renderDetail(<BotSessionPage />);

    const fact = (await screen.findByText('Preset')).parentElement as HTMLElement;
    expect(await within(fact).findByText('MA Crossover (Algo 6)')).toBeInTheDocument();
    expect(within(fact).getByText('Customized')).toBeInTheDocument();
  });

  it('falls back to the raw key when the preset is not in the catalog', async () => {
    mockedGet.mockImplementation(
      routeGet({ session: { ...bot, preset_key: 'retired_preset' } }),
    );
    renderDetail(<BotSessionPage />);

    const fact = (await screen.findByText('Preset')).parentElement as HTMLElement;
    expect(within(fact).getByText('retired_preset')).toBeInTheDocument();
  });

  it('links an orchestrator-deployed bot to its orchestrator', async () => {
    mockedGet.mockImplementation(
      routeGet({
        session: {
          ...bot,
          origin: 'orchestrator',
          orchestrator_id: 'o1',
          orchestrator_label: 'Core rotation',
        },
      }),
    );
    renderDetail(<BotSessionPage />);

    const fact = (await screen.findByText('Deployed by')).parentElement as HTMLElement;
    expect(within(fact).getByRole('link', { name: 'Core rotation' })).toHaveAttribute(
      'href',
      '/orchestrators/o1',
    );
  });

  it('returns an orchestrator-deployed bot to its orchestrator', async () => {
    mockedGet.mockImplementation(
      routeGet({
        session: {
          ...bot,
          origin: 'orchestrator',
          orchestrator_id: 'o1',
          orchestrator_label: 'Core rotation',
        },
      }),
    );
    renderDetail(<BotSessionPage />);

    expect(
      await screen.findByRole('link', { name: /Back to Core rotation/ }),
    ).toHaveAttribute('href', '/orchestrators/o1');
    expect(screen.queryByRole('link', { name: /Back to bots/ })).not.toBeInTheDocument();
  });

  it('shows no orchestrator link for a manual bot', async () => {
    mockedGet.mockImplementation(routeGet());
    renderDetail(<BotSessionPage />);

    await screen.findByText('Preset');
    expect(screen.queryByText('Deployed by')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Back to bots/ })).toHaveAttribute(
      'href',
      '/bots',
    );
  });

  it('heads an unlabelled bot with its display name and strategy name', async () => {
    mockedGet.mockImplementation(
      routeGet({
        session: { ...bot, label: null, display_name: 'MA Crossover (Algo 6) · AAPL' },
      }),
    );
    renderDetail(<BotSessionPage />);

    expect(
      await screen.findByRole('heading', { name: 'MA Crossover (Algo 6) · AAPL' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Moving-Average Crossover')).toBeInTheDocument();
    expect(screen.queryByText('ma_crossover')).not.toBeInTheDocument();
  });
});
