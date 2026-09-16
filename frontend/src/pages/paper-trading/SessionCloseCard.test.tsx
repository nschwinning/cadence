import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { AxiosError } from 'axios';
import { SessionCloseCard } from './SessionCloseCard';
import { apiClient } from '../../api/client';
import type { AIPortfolioRunDetail, ClosedPosition } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedPost = vi.mocked(apiClient.post);

function closedPosition(
  ticker: string,
  realized_pnl: number,
): ClosedPosition {
  return {
    id: `cp-${ticker}`,
    session_id: 's1',
    ai_portfolio_event_id: 'evt-close',
    ticker,
    quantity: 10,
    entry_price: 100,
    exit_price: 100 + realized_pnl / 10,
    entry_date: '2026-09-01T00:00:00Z',
    exit_date: '2026-09-16T00:00:00Z',
    realized_pnl,
    return_pct: realized_pnl / 1000,
    holding_days: 15,
  };
}

const RUN_DETAIL: AIPortfolioRunDetail = {
  event: {
    id: 'evt-close',
    session_id: 's1',
    portfolio_id: 'p1',
    event_type: 'close',
    status: 'succeeded',
    request_payload: null,
    result_payload: null,
    actions_taken: [
      { ticker: 'AAPL', side: 'sell', executed: true },
      { ticker: 'MSFT', side: 'sell', executed: true },
    ],
    research: null,
    error: null,
    duration_ms: 120,
    created_at: '2026-09-16T00:00:00Z',
    updated_at: '2026-09-16T00:00:00Z',
  },
  trades: [],
  closed_positions: [closedPosition('AAPL', 250), closedPosition('MSFT', -50)],
};

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

describe('SessionCloseCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('confirms then closes and shows the liquidation summary', async () => {
    mockedPost.mockResolvedValue({ data: RUN_DETAIL });
    const user = userEvent.setup();

    renderCard(<SessionCloseCard sessionId="s1" status="active" />);

    // First click reveals the confirm step; no request yet.
    await user.click(screen.getByRole('button', { name: 'Close portfolio' }));
    expect(mockedPost).not.toHaveBeenCalled();
    expect(screen.getByText(/Are you sure/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Confirm close' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/ai-portfolio/sessions/s1/close',
      {},
    );
    // Success summary: 2 positions, net realized P&L (250 + -50 = 200).
    expect(await screen.findByText('Portfolio closed')).toBeInTheDocument();
    expect(
      screen.getByText(/2 positions liquidated/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/View the close run/i)).toBeInTheDocument();
  });

  it('cancels the confirm step without closing', async () => {
    const user = userEvent.setup();
    renderCard(<SessionCloseCard sessionId="s1" status="active" />);

    await user.click(screen.getByRole('button', { name: 'Close portfolio' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByText(/Are you sure/i)).not.toBeInTheDocument();
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('disables the action and explains when the session is not active', () => {
    renderCard(<SessionCloseCard sessionId="s1" status="stopped" />);

    expect(
      screen.getByRole('button', { name: 'Close portfolio' }),
    ).toBeDisabled();
    expect(
      screen.getByText(/Only an active portfolio can be closed/i),
    ).toBeInTheDocument();
  });

  it('surfaces a 409 not-eligible error message', async () => {
    mockedPost.mockRejectedValue(
      new AxiosError('conflict', 'ERR', undefined, undefined, {
        status: 409,
        data: {},
      } as never),
    );
    const user = userEvent.setup();
    renderCard(<SessionCloseCard sessionId="s1" status="active" />);

    await user.click(screen.getByRole('button', { name: 'Close portfolio' }));
    await user.click(screen.getByRole('button', { name: 'Confirm close' }));

    expect(
      await screen.findByText(/cannot be closed/i),
    ).toBeInTheDocument();
  });
});
