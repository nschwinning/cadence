import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AdminPage } from './AdminPage';
import { apiClient } from '../../api/client';
import type { AdminAccount, AdminPosition } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

function position(overrides: Partial<AdminPosition>): AdminPosition {
  return {
    symbol: 'XOM',
    asset_class: 'us_equity',
    broker_quantity: 10,
    cadence_quantity: 0,
    orphan_quantity: 10,
    market_value: 1100,
    status: 'orphan',
    pending_order: false,
    flattenable: true,
    restorable: false,
    restore_quantity: 0,
    ...overrides,
  };
}

function account(overrides: Partial<AdminAccount> = {}): AdminAccount {
  return {
    broker_available: true,
    reason: null,
    account: { cash: 20000, buying_power: 40000, portfolio_value: 95000, currency: 'USD' },
    cash_check: {
      contributors: [
        { kind: 'portfolio', id: 'p1', label: 'Growth', amount: 9000 },
        { kind: 'orchestrator', id: 'o1', label: 'First Orchestrator', amount: 3500 },
      ],
      committed_total: 12500,
      account_cash: 20000,
      difference: 7500,
      shortfall: false,
      reported_cash: 20000,
      short_proceeds: 0,
    },
    open_orders: [],
    unresolved_orders: [],
    positions: [
      position({}),
      position({
        symbol: 'AAPL',
        broker_quantity: 5,
        cadence_quantity: 5,
        orphan_quantity: 0,
        status: 'matched',
        flattenable: false,
      }),
      position({
        symbol: 'CVX',
        orphan_quantity: 2,
        pending_order: true,
        flattenable: false,
      }),
    ],
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminPage />
    </QueryClientProvider>,
  );
}

function rowOf(symbol: string): HTMLElement {
  return screen.getByRole('cell', { name: new RegExp(`^${symbol}`) }).closest('tr') as HTMLElement;
}

describe('AdminPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the account figures and the itemised cash check', async () => {
    mockedGet.mockResolvedValue({ data: account() });

    renderPage();

    expect(await screen.findByText('$40,000.00')).toBeInTheDocument(); // buying power
    expect(screen.getByText('$95,000.00')).toBeInTheDocument();
    expect(screen.getByText('Growth')).toBeInTheDocument();
    expect(screen.getByText('Orchestrator (free capital)')).toBeInTheDocument();
    expect(screen.getByText('$12,500.00')).toBeInTheDocument();
    expect(screen.getByTestId('cash-difference')).toHaveTextContent('$7,500.00');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('warns on a cash shortfall', async () => {
    const base = account();
    mockedGet.mockResolvedValue({
      data: account({
        cash_check: { ...base.cash_check!, difference: -2000, shortfall: true },
      }),
    });

    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Cadence has committed $2,000.00 more cash than the account holds',
    );
  });

  it('offers Flatten only on flattenable rows and explains the others', async () => {
    mockedGet.mockResolvedValue({ data: account() });

    renderPage();
    await screen.findByText('$40,000.00');

    expect(within(rowOf('XOM')).getByRole('button', { name: 'Flatten XOM' })).toBeInTheDocument();
    expect(within(rowOf('AAPL')).getByText('Matched')).toBeInTheDocument();
    expect(within(rowOf('AAPL')).queryByRole('button')).not.toBeInTheDocument();
    expect(within(rowOf('CVX')).getByText('Pending order')).toBeInTheDocument();
    expect(within(rowOf('CVX')).queryByRole('button')).not.toBeInTheDocument();
  });

  it('cancelling the confirmation submits nothing', async () => {
    mockedGet.mockResolvedValue({ data: account() });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Flatten XOM' }));
    const dialog = screen.getByRole('dialog', { name: 'Confirm flatten' });
    expect(within(dialog).getByText('XOM')).toBeInTheDocument();
    expect(within(dialog).getByText(/recomputed when the order is placed/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('confirming posts only the symbol and shows the outcome', async () => {
    mockedGet.mockResolvedValue({ data: account() });
    mockedPost.mockResolvedValue({
      data: {
        outcomes: [
          { symbol: 'XOM', result: 'sold', quantity: 10, order_id: 'o-1', reason: null },
        ],
      },
    });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Flatten XOM' }));
    await user.click(screen.getByRole('button', { name: 'Sell' }));

    expect(mockedPost).toHaveBeenCalledWith('/api/v1/admin/flatten-orphans', { symbol: 'XOM' });
    expect(await screen.findByTestId('flatten-outcomes')).toHaveTextContent('XOM: sold 10');
  });

  it('flatten all posts a null symbol and reports skips and failures', async () => {
    mockedGet.mockResolvedValue({ data: account() });
    mockedPost.mockResolvedValue({
      data: {
        outcomes: [
          { symbol: 'XOM', result: 'skipped', quantity: null, order_id: null, reason: 'market_closed' },
          { symbol: 'BTC-USD', result: 'failed', quantity: 0.5, order_id: null, reason: 'insufficient qty' },
        ],
      },
    });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Flatten all orphans' }));
    await user.click(screen.getByRole('button', { name: 'Sell' }));

    expect(mockedPost).toHaveBeenCalledWith('/api/v1/admin/flatten-orphans', { symbol: null });
    const outcomes = await screen.findByTestId('flatten-outcomes');
    expect(outcomes).toHaveTextContent('XOM: skipped — equity market is closed');
    expect(outcomes).toHaveTextContent('BTC-USD: failed — insufficient qty');
  });

  it('hides Flatten all when nothing is flattenable', async () => {
    mockedGet.mockResolvedValue({
      data: account({ positions: [position({ status: 'matched', orphan_quantity: 0, flattenable: false })] }),
    });

    renderPage();
    await screen.findByText('$40,000.00');

    expect(screen.queryByRole('button', { name: 'Flatten all orphans' })).not.toBeInTheDocument();
  });

  it('says the broker is unavailable and shows no figures', async () => {
    mockedGet.mockResolvedValue({
      data: account({
        broker_available: false,
        reason: 'Alpaca connection error: timed out',
        account: null,
        cash_check: null,
        positions: [],
      }),
    });

    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent('Broker unavailable');
    expect(screen.getByRole('alert')).toHaveTextContent('timed out');
    expect(screen.queryByText('Cash check')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Flatten/ })).not.toBeInTheDocument();
  });

  it('restores a short row after confirmation, posting only the symbol', async () => {
    mockedGet.mockResolvedValue({
      data: account({
        positions: [
          position({
            symbol: 'TSLA',
            broker_quantity: -6,
            cadence_quantity: 4,
            orphan_quantity: 0,
            status: 'short',
            flattenable: false,
            restorable: true,
            restore_quantity: 10,
          }),
        ],
      }),
    });
    mockedPost.mockResolvedValue({
      data: {
        outcomes: [
          { symbol: 'TSLA', result: 'bought', quantity: 10, order_id: 'o-2', reason: null },
        ],
      },
    });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Restore TSLA' }));
    const dialog = screen.getByRole('dialog', { name: 'Confirm restore' });
    expect(within(dialog).getByText('10')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Buy' }));

    expect(mockedPost).toHaveBeenCalledWith('/api/v1/admin/restore-positions', {
      symbol: 'TSLA',
    });
    expect(await screen.findByTestId('flatten-outcomes')).toHaveTextContent(
      'TSLA: bought 10',
    );
  });

  it('restore all posts a null symbol and cancel sends nothing', async () => {
    mockedGet.mockResolvedValue({
      data: account({
        positions: [
          position({
            symbol: 'NVDA',
            status: 'shortfall',
            flattenable: false,
            restorable: true,
            restore_quantity: 4,
          }),
        ],
      }),
    });
    mockedPost.mockResolvedValue({ data: { outcomes: [] } });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Restore all' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mockedPost).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Restore all' }));
    await user.click(screen.getByRole('button', { name: 'Buy' }));
    expect(mockedPost).toHaveBeenCalledWith('/api/v1/admin/restore-positions', {
      symbol: null,
    });
  });

  it('shows the short-sale proceeds excluded from the cash', async () => {
    const base = account();
    mockedGet.mockResolvedValue({
      data: account({
        cash_check: {
          ...base.cash_check!,
          reported_cash: 294000,
          short_proceeds: 201000,
          account_cash: 93000,
        },
      }),
    });

    renderPage();

    expect(await screen.findByTestId('short-proceeds')).toHaveTextContent('$201,000.00');
    expect(screen.getByText('$294,000.00')).toBeInTheDocument();
  });

  it('lists unresolved orders and shows the reconcile result', async () => {
    mockedGet.mockResolvedValue({
      data: account({
        unresolved_orders: [
          {
            client_order_id: 'cad-b-1',
            owner_kind: 'bot',
            owner_label: 'Turtle Breakout (Algo 25) · MSFT',
            ticker: 'MSFT',
            side: 'sell',
            quantity: 5,
            state: 'submitted',
            broker_status: 'submitted',
            error: null,
            created_at: '2026-11-11T14:40:00Z',
          },
        ],
      }),
    });
    mockedPost.mockResolvedValue({ data: { booked: 1, closed: 0, remaining: 0 } });
    const user = userEvent.setup();

    renderPage();
    expect(
      await screen.findByText('Turtle Breakout (Algo 25) · MSFT'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Reconcile now' }));

    expect(mockedPost).toHaveBeenCalledWith('/api/v1/admin/reconcile-orders');
    expect(await screen.findByTestId('reconcile-result')).toHaveTextContent(
      'Reconciled: 1 booked, 0 closed, 0 still open.',
    );
  });

  it('rows that are matched or pending offer no action', async () => {
    mockedGet.mockResolvedValue({ data: account() });

    renderPage();
    await screen.findByText('$40,000.00');

    expect(within(rowOf('AAPL')).queryByRole('button')).not.toBeInTheDocument();
    expect(within(rowOf('CVX')).queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Restore all' })).not.toBeInTheDocument();
  });

  it('shows the remainder note when a short cover is still filling', async () => {
    mockedGet.mockResolvedValue({
      data: account({
        positions: [
          position({
            symbol: 'PSA',
            broker_quantity: -75,
            cadence_quantity: 1,
            orphan_quantity: 0,
            status: 'short',
            flattenable: false,
            restorable: true,
            restore_quantity: 76,
          }),
        ],
      }),
    });
    mockedPost.mockResolvedValue({
      data: {
        outcomes: [
          {
            symbol: 'PSA',
            result: 'bought',
            quantity: 75,
            order_id: 'o-3',
            reason: 'cover of 75 still filling; run Restore again to buy the remaining 1',
          },
        ],
      },
    });
    const user = userEvent.setup();

    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Restore PSA' }));
    await user.click(screen.getByRole('button', { name: 'Buy' }));

    expect(await screen.findByTestId('flatten-outcomes')).toHaveTextContent(
      'PSA: bought 75 — cover of 75 still filling; run Restore again to buy the remaining 1',
    );
  });
});
