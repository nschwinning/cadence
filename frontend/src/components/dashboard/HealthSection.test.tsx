import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { HealthSection } from './HealthSection';
import { apiClient } from '../../api/client';
import type {
  AdminAccount,
  AdminPosition,
  AdminPositionStatus,
  DashboardTickHealth,
} from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const healthyTicks: DashboardTickHealth = {
  latest: {
    ran_at: new Date(Date.now() - 2 * 60_000).toISOString(),
    market_open: true,
    processed: 3,
    skipped: 0,
    failed: 0,
    reconciled: 0,
    error: null,
  },
  stale: false,
  failing_bots: [],
};

function row(symbol: string, status: AdminPositionStatus): AdminPosition {
  return {
    symbol,
    asset_class: 'equity',
    broker_quantity: 1,
    cadence_quantity: 1,
    orphan_quantity: 0,
    market_value: 100,
    status,
    pending_order: false,
    flattenable: false,
    restorable: false,
    restore_quantity: 0,
  };
}

function account(positions: AdminPosition[] = [], unresolved = 0): AdminAccount {
  return {
    broker_available: true,
    reason: null,
    account: { cash: 1, buying_power: 1, portfolio_value: 1, currency: 'USD' },
    cash_check: {
      contributors: [],
      committed_total: 0,
      account_cash: 1,
      difference: 1,
      shortfall: false,
      reported_cash: 1,
      short_proceeds: 0,
    },
    open_orders: [],
    positions,
    unresolved_orders: Array.from({ length: unresolved }, (_, i) => ({
      client_order_id: `cad-b-${i}`,
      owner_kind: 'bot',
      owner_label: 'Bot',
      ticker: 'AAPL',
      side: 'buy',
      quantity: 1,
      state: 'submitted',
      broker_status: null,
      error: null,
      created_at: '2026-11-11T14:00:00Z',
    })),
  };
}

function renderHealth(ticks: DashboardTickHealth, data: AdminAccount | Error = account()) {
  if (data instanceof Error) mockedGet.mockRejectedValue(data);
  else mockedGet.mockResolvedValue({ data });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <HealthSection tickHealth={ticks} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('HealthSection', () => {
  beforeEach(() => vi.clearAllMocks());

  it('states all healthy when ticks run, no bot fails and the account matches', async () => {
    renderHealth(healthyTicks);

    expect(await screen.findByText('All healthy')).toBeInTheDocument();
    expect(screen.getByTestId('latest-tick')).toHaveTextContent('3 processed, 0 failed');
    expect(screen.getByTestId('consistency')).toHaveTextContent(
      'Account matches Cadence’s records.',
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('warns when ticks have stopped', async () => {
    renderHealth({ ...healthyTicks, stale: true });

    expect(await screen.findByRole('alert')).toHaveTextContent('Bot ticks have stopped');
    expect(screen.queryByText('All healthy')).not.toBeInTheDocument();
  });

  it('shows a crashed last tick with its error', async () => {
    renderHealth({
      ...healthyTicks,
      latest: { ...healthyTicks.latest!, error: 'reconciliation exploded' },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The last tick crashed: reconciliation exploded',
    );
  });

  it('lists failing bots with a link, their count and error', async () => {
    renderHealth({
      ...healthyTicks,
      failing_bots: [
        {
          id: 'b1',
          display_name: 'Turtle Breakout (Algo 25) · MSFT',
          consecutive_failures: 2,
          last_failure_at: '2026-11-11T14:40:00Z',
          last_failure_error: 'Alpaca API error: insufficient buying power',
        },
      ],
    });

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('1 bot is failing');
    expect(alert).toHaveTextContent('2 failed ticks in a row');
    expect(alert).toHaveTextContent('insufficient buying power');
    expect(
      screen.getByRole('link', { name: 'Turtle Breakout (Algo 25) · MSFT' }),
    ).toHaveAttribute('href', '/bots/b1');
  });

  it('counts account inconsistencies and links to Admin', async () => {
    renderHealth(
      healthyTicks,
      account([row('TSLA', 'short'), row('NVDA', 'short'), row('AAPL', 'matched')], 1),
    );

    const line = await screen.findByTestId('consistency');
    expect(line).toHaveTextContent('2 shorts');
    expect(line).toHaveTextContent('1 unresolved orders');
    expect(line).toHaveTextContent('0 orphans');
    expect(screen.getByRole('link', { name: 'Admin →' })).toHaveAttribute('href', '/admin');
    expect(screen.queryByText('All healthy')).not.toBeInTheDocument();
  });

  it('says the broker account is unavailable but still shows tick health', async () => {
    renderHealth(healthyTicks, new Error('503'));

    expect(await screen.findByText('Broker account unavailable')).toBeInTheDocument();
    expect(screen.getByTestId('latest-tick')).toHaveTextContent('3 processed');
    expect(screen.queryByText('All healthy')).not.toBeInTheDocument();
  });

  it('says when no tick has been recorded yet', async () => {
    renderHealth({ latest: null, stale: false, failing_bots: [] });

    expect(await screen.findByTestId('latest-tick')).toHaveTextContent('none recorded yet');
  });
});
