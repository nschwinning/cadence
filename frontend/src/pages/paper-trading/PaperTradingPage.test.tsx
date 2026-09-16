import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { PaperTradingPage } from './PaperTradingPage';
import { apiClient } from '../../api/client';
import type {
  PaperTradingSession,
  PaperTradingSessionListResponse,
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
  total_trades: 12,
  total_pnl: 1500,
  session_metadata: null,
  schedule_mode: 'DAILY_REBALANCING',
  archived_at: null,
  rebalance_prompt_version: 1,
};

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

describe('PaperTradingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a session row linking to its detail page', async () => {
    const body: PaperTradingSessionListResponse = {
      items: [session],
      total: 1,
    };
    mockedGet.mockResolvedValue({ data: body });

    renderWithClient(<PaperTradingPage />);

    const link = await screen.findByRole('link', { name: 'ai-momentum' });
    expect(link).toHaveAttribute('href', '/paper-trading/s1');
    expect(screen.getByText('active')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('shows an empty state with no sessions', async () => {
    mockedGet.mockResolvedValue({ data: { items: [], total: 0 } });

    renderWithClient(<PaperTradingPage />);

    expect(
      await screen.findByText(/No paper-trading sessions yet/i),
    ).toBeInTheDocument();
  });

  it('toggling "Show archived" refetches with include_archived', async () => {
    mockedGet.mockResolvedValue({ data: { items: [session], total: 1 } });
    const user = userEvent.setup();

    renderWithClient(<PaperTradingPage />);
    await screen.findByRole('link', { name: 'ai-momentum' });

    // The default list request omits the flag.
    expect(mockedGet).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions',
      { params: { limit: 50 } },
    );

    await user.click(screen.getByLabelText(/Show archived/i));

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith(
        '/api/v1/paper-trading/sessions',
        { params: { limit: 50, include_archived: true } },
      );
    });
  });

  it('archives a stopped session via the row action and refetches the list', async () => {
    const stopped: PaperTradingSession = {
      ...session,
      status: 'stopped',
    };
    mockedGet.mockResolvedValue({ data: { items: [stopped], total: 1 } });
    mockedPost.mockResolvedValue({
      data: { ...stopped, archived_at: '2026-09-16T00:00:00Z' },
    });
    const user = userEvent.setup();

    renderWithClient(<PaperTradingPage />);
    await screen.findByRole('link', { name: 'ai-momentum' });

    await user.click(screen.getByRole('button', { name: 'Archive' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/archive',
      {},
    );
    // Success invalidates the sessions list, triggering a refetch.
    await waitFor(() => {
      expect(mockedGet.mock.calls.length).toBeGreaterThan(1);
    });
  });

  it('unarchives an archived session via the row action', async () => {
    const archived: PaperTradingSession = {
      ...session,
      status: 'stopped',
      archived_at: '2026-09-16T00:00:00Z',
    };
    mockedGet.mockResolvedValue({ data: { items: [archived], total: 1 } });
    mockedPost.mockResolvedValue({ data: { ...archived, archived_at: null } });
    const user = userEvent.setup();

    renderWithClient(<PaperTradingPage />);
    await screen.findByRole('link', { name: 'ai-momentum' });
    expect(screen.getByText('Archived')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Unarchive' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/s1/unarchive',
      {},
    );
  });
});
