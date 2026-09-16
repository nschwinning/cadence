import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { PortfoliosPage } from './PortfoliosPage';
import { apiClient } from '../../api/client';
import type {
  PaperTradingSession,
  Portfolio,
  PortfolioListResponse,
} from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

const portfolio: Portfolio = {
  id: 'p1',
  name: 'Momentum Growth',
  description: null,
  stocks: ['AAPL', 'MSFT'],
  max_allocation_pct: 0.25,
  source: 'ai_managed',
  risk_profile: 'balanced',
  source_run_id: null,
  created_at: '2026-09-10T00:00:00Z',
  archived_at: null,
};

const activeSession: PaperTradingSession = {
  id: 's1',
  portfolio_id: 'p1',
  strategy_key: 'ai-momentum',
  status: 'active',
  allocated_capital: 100000,
  max_allocation_pct: 0.25,
  created_at: '2026-09-10T00:00:00Z',
  updated_at: '2026-09-12T00:00:00Z',
  last_run_at: null,
  total_trades: 0,
  total_pnl: 0,
  session_metadata: null,
  schedule_mode: 'DAILY_REBALANCING',
  archived_at: null,
  rebalance_prompt_version: 1,
};

/**
 * Route the mocked GETs: the portfolios list to `portfolios`, the sessions list
 * (used to derive archive eligibility) to `sessions`.
 */
function installGet(portfolios: Portfolio[], sessions: PaperTradingSession[]) {
  mockedGet.mockImplementation((url: string) => {
    if (url.endsWith('/paper-trading/sessions')) {
      return Promise.resolve({
        data: { items: sessions, total: sessions.length },
      });
    }
    return Promise.resolve({
      data: { items: portfolios, total: portfolios.length },
    });
  });
}

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PortfoliosPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the build card and a stored-portfolio row linking to detail', async () => {
    const body: PortfolioListResponse = { items: [portfolio], total: 1 };
    mockedGet.mockResolvedValue({ data: body });

    renderWithClient(<PortfoliosPage />);

    expect(screen.getByText('Build an AI portfolio')).toBeInTheDocument();

    const link = await screen.findByRole('link', { name: 'Momentum Growth' });
    expect(link).toHaveAttribute('href', '/portfolios/p1');
    expect(screen.getByText('25%')).toBeInTheDocument();
  });

  it('shows an empty state when there are no portfolios', async () => {
    mockedGet.mockResolvedValue({ data: { items: [], total: 0 } });

    renderWithClient(<PortfoliosPage />);

    expect(
      await screen.findByText(/No portfolios yet/i),
    ).toBeInTheDocument();
  });

  it('toggling "Show archived" refetches with include_archived', async () => {
    installGet([portfolio], []);
    const user = userEvent.setup();

    renderWithClient(<PortfoliosPage />);
    await screen.findByRole('link', { name: 'Momentum Growth' });

    expect(mockedGet).toHaveBeenCalledWith('/api/v1/portfolios', {
      params: { include_legacy: true, limit: 50 },
    });

    await user.click(screen.getByLabelText(/Show archived/i));

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith('/api/v1/portfolios', {
        params: { include_legacy: true, limit: 50, include_archived: true },
      });
    });
  });

  it('archives a portfolio with no active sessions and refetches', async () => {
    installGet([portfolio], []);
    mockedPost.mockResolvedValue({
      data: { ...portfolio, archived_at: '2026-09-16T00:00:00Z' },
    });
    const user = userEvent.setup();

    renderWithClient(<PortfoliosPage />);
    await screen.findByRole('link', { name: 'Momentum Growth' });

    await user.click(screen.getByRole('button', { name: 'Archive' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/portfolios/p1/archive',
      {},
    );
    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith('/api/v1/portfolios', {
        params: { include_legacy: true, limit: 50 },
      });
      // The success invalidation refetches both portfolios and sessions.
      expect(mockedGet.mock.calls.length).toBeGreaterThan(2);
    });
  });

  it('blocks archiving a portfolio that has an active session', async () => {
    installGet([portfolio], [activeSession]);

    renderWithClient(<PortfoliosPage />);
    await screen.findByRole('link', { name: 'Momentum Growth' });

    // No Archive button — an "In use" note replaces it.
    expect(
      screen.queryByRole('button', { name: 'Archive' }),
    ).not.toBeInTheDocument();
    expect(screen.getByText('In use')).toBeInTheDocument();
  });

  it('unarchives an archived portfolio via the row action', async () => {
    const archived: Portfolio = {
      ...portfolio,
      archived_at: '2026-09-16T00:00:00Z',
    };
    installGet([archived], []);
    mockedPost.mockResolvedValue({ data: { ...archived, archived_at: null } });
    const user = userEvent.setup();

    renderWithClient(<PortfoliosPage />);
    await screen.findByRole('link', { name: 'Momentum Growth' });
    expect(screen.getByText('Archived')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Unarchive' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/portfolios/p1/unarchive',
      {},
    );
  });
});
