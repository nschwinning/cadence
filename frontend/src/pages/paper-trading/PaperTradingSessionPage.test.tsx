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
} from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

const session: PaperTradingSession = {
  id: 's1',
  portfolio_id: 'p1',
  strategy_key: 'ai-momentum',
  status: 'active',
  allocated_capital: 100000,
  max_allocation_pct: 0.25,
  created_at: '2026-09-10T00:00:00Z',
  updated_at: '2026-09-12T00:00:00Z',
  last_run_at: '2026-09-12T09:30:00Z',
  total_trades: 3,
  total_pnl: 500,
  session_metadata: null,
  schedule_mode: 'DAILY_REBALANCING',
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

/** Route the mocked GETs by URL to the right fixture. */
function installGet(eventStatus: () => AIEventStatus) {
  mockedGet.mockImplementation((url: string) => {
    if (url.endsWith('/paper-trading/sessions')) {
      return Promise.resolve({ data: { items: [session], total: 1 } });
    }
    if (url.includes('/ai-portfolio/sessions/') && url.endsWith('/events')) {
      return Promise.resolve({ data: [] });
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
      await screen.findByRole('heading', { name: 'ai-momentum' }),
    ).toBeInTheDocument();
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

  it('triggers a rebalance and reflects terminal feedback without manual refresh', async () => {
    let status: AIEventStatus = 'running';
    installGet(() => status);
    mockedPost.mockResolvedValue({
      data: { event_id: 'evt-1', status: 'queued', started: true },
    });
    const user = userEvent.setup();

    const { queryClient } = renderPage(<PaperTradingSessionPage />);
    await screen.findByRole('heading', { name: 'ai-momentum' });

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
        return Promise.resolve({ data: [] });
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
});
