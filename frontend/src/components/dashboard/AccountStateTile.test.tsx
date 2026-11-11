import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AccountStateTile } from './AccountStateTile';
import { apiClient } from '../../api/client';
import type { AdminAccount, AdminPosition } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

function short(symbol: string): AdminPosition {
  return {
    symbol,
    asset_class: 'equity',
    broker_quantity: -10,
    cadence_quantity: 0,
    orphan_quantity: 0,
    market_value: -1000,
    status: 'short',
    pending_order: false,
    flattenable: false,
    restorable: true,
    restore_quantity: 10,
  };
}

function account(
  free: number,
  positions: AdminPosition[] = [],
  shortProceeds = 0,
  buyingPower = 100000,
): AdminAccount {
  return {
    broker_available: true,
    reason: null,
    account: { cash: 100000, buying_power: buyingPower, portfolio_value: 100000, currency: 'USD' },
    cash_check: {
      contributors: [],
      committed_total: 75000,
      account_cash: 75000 + free,
      difference: free,
      shortfall: free < 0,
      reported_cash: 75000 + free + shortProceeds,
      short_proceeds: shortProceeds,
    },
    open_orders: [],
    positions,
    unresolved_orders: [],
  };
}

function renderTile(data: AdminAccount | Error) {
  if (data instanceof Error) mockedGet.mockRejectedValue(data);
  else mockedGet.mockResolvedValue({ data });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AccountStateTile />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AccountStateTile', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows free capital and context with no warning on a healthy account', async () => {
    renderTile(account(25000));

    expect(await screen.findByTestId('free-capital')).toHaveTextContent('$25,000.00');
    expect(screen.getByText(/committed by Cadence \$75,000\.00/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Admin →' })).toHaveAttribute('href', '/admin');
    expect(mockedGet).toHaveBeenCalledWith('/api/v1/admin/account');
  });

  it('warns amber when free capital is below $1,000', async () => {
    renderTile(account(600));

    expect(await screen.findByRole('note')).toHaveTextContent('Low capital');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('warns red when no capital is left', async () => {
    renderTile(account(-2000));

    expect(await screen.findByRole('alert')).toHaveTextContent('No capital left');
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('warns red about short positions with their count and value', async () => {
    renderTile(account(25000, [short('TSLA'), short('NVDA')], 201000));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '2 short positions worth $201,000.00',
    );
  });

  it('shows both red warnings together', async () => {
    renderTile(account(0, [short('TSLA')], 5000));

    const alerts = await screen.findAllByRole('alert');
    expect(alerts.map((a) => a.textContent)).toEqual([
      expect.stringContaining('No capital left'),
      expect.stringContaining('1 short position worth $5,000.00'),
    ]);
  });

  it('says the broker is unavailable instead of showing figures', async () => {
    renderTile({ ...account(25000), broker_available: false, reason: 'timed out', cash_check: null });

    expect(await screen.findByText('Broker unavailable')).toBeInTheDocument();
    expect(screen.getByText('timed out')).toBeInTheDocument();
    expect(screen.queryByTestId('free-capital')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('treats a failed request as unavailable', async () => {
    renderTile(new Error('503'));

    expect(await screen.findByText('Broker unavailable')).toBeInTheDocument();
  });

  it('caps free capital at the buying power', async () => {
    renderTile(account(25000, [], 0, 8000));

    expect(await screen.findByTestId('free-capital')).toHaveTextContent('$8,000.00');
    expect(screen.getByTestId('buying-power')).toHaveTextContent('$8,000.00');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('warns red when buying power is gone even though cash is free', async () => {
    renderTile(account(25000, [short('TSLA')], 201000, 0));

    expect(await screen.findByTestId('free-capital')).toHaveTextContent('$0.00');
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.map((a) => a.textContent)).toEqual([
      expect.stringContaining('No buying power'),
      expect.stringContaining('1 short position worth $201,000.00'),
    ]);
    expect(screen.queryByText(/No capital left/)).not.toBeInTheDocument();
  });

  it('flags low capital when buying power is the limit', async () => {
    renderTile(account(25000, [], 0, 500));

    expect(await screen.findByRole('note')).toHaveTextContent('Low capital');
  });
});
