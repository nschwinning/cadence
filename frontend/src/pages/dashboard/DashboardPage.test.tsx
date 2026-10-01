import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { DashboardPage } from './DashboardPage';
import { apiClient } from '../../api/client';
import { makeOverview, makeSession } from './fixtures';
import type { DashboardOverview, HealthResponse } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
  getHealth: vi.fn(() =>
    Promise.resolve({ status: 'ok', database: 'connected' }),
  ),
}));

const mockedGet = vi.mocked(apiClient.get);

const sessions = [
  makeSession({ id: 'a', label: 'Portfolio A', current_value: 11000, pnl: 1000 }),
  makeSession({ id: 'b', label: 'Portfolio B', current_value: 20000, pnl: 0 }),
];

const overview1M: DashboardOverview = makeOverview({
  range: '1M',
  sessions,
  universe_performers: {
    best: [{ asset_id: 1, ticker: 'TECH', name: 'Tech Co', return_pct: 0.2 }],
    worst: [{ asset_id: 2, ticker: 'FIN', name: 'Fin Co', return_pct: -0.1 }],
  },
});

const overviewYTD: DashboardOverview = makeOverview({
  range: 'YTD',
  sessions,
  universe_performers: {
    best: [{ asset_id: 3, ticker: 'GOLD', name: 'Gold Co', return_pct: 0.5 }],
    worst: [{ asset_id: 2, ticker: 'FIN', name: 'Fin Co', return_pct: -0.3 }],
  },
});

const health: HealthResponse = { status: 'ok', database: 'connected' };

type GetConfig = { params?: { range?: string } };

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGet.mockImplementation((url: string, config?: unknown) => {
      if (url.includes('/dashboard/overview')) {
        const range = (config as GetConfig | undefined)?.params?.range;
        return Promise.resolve({
          data: range === 'YTD' ? overviewYTD : overview1M,
        });
      }
      if (url.includes('/health')) return Promise.resolve({ data: health });
      return Promise.resolve({ data: {} });
    });
  });

  it('renders the hero tiles and sections for the default range', async () => {
    renderWithClient(<DashboardPage />);
    expect(await screen.findByText('Total value')).toBeInTheDocument();
    // both sessions selected by default: $11,000 + $20,000
    expect(screen.getByText('$31,000.00')).toBeInTheDocument();
    expect(screen.getByText('Portfolio leaderboard')).toBeInTheDocument();
    expect(screen.getByText('Automation')).toBeInTheDocument();
    expect(screen.getByText('Recent activity')).toBeInTheDocument();
    expect(screen.getByText('Top performers')).toBeInTheDocument();
  });

  it('refetches keyed by range and updates performers while balance stays stable', async () => {
    renderWithClient(<DashboardPage />);
    await screen.findByText('TECH');
    expect(screen.getByText('Sectors covered')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'YTD' }));

    await waitFor(() => expect(screen.getByText('GOLD')).toBeInTheDocument());
    expect(screen.queryByText('TECH')).not.toBeInTheDocument();
    // balance summary is range-independent — eligible count unchanged
    expect(screen.getByText('90')).toBeInTheDocument();
    expect(
      mockedGet.mock.calls.some(
        (c) =>
          String(c[0]).includes('/dashboard/overview') &&
          (c[1] as GetConfig | undefined)?.params?.range === 'YTD',
      ),
    ).toBe(true);
  });

  it('deselecting a portfolio re-aggregates tiles and drops its leaderboard row without refetching', async () => {
    renderWithClient(<DashboardPage />);
    await screen.findByText('$31,000.00');

    const overviewCallsBefore = mockedGet.mock.calls.filter((c) =>
      String(c[0]).includes('/dashboard/overview'),
    ).length;

    await userEvent.click(
      screen.getByRole('checkbox', { name: /Portfolio B/ }),
    );

    // the Total value hero tile recomputes to just Portfolio A
    const totalTile = () =>
      screen.getByText('Total value').closest('div') as HTMLElement;
    await waitFor(() =>
      expect(within(totalTile()).getByText('$11,000.00')).toBeInTheDocument(),
    );
    expect(within(totalTile()).queryByText('$31,000.00')).not.toBeInTheDocument();

    // leaderboard now links to only Portfolio A
    const leaderLinks = screen
      .getAllByRole('link')
      .filter((l) => l.getAttribute('href')?.startsWith('/paper-trading/'));
    expect(leaderLinks).toHaveLength(1);
    expect(leaderLinks[0]).toHaveTextContent('Portfolio A');

    const overviewCallsAfter = mockedGet.mock.calls.filter((c) =>
      String(c[0]).includes('/dashboard/overview'),
    ).length;
    expect(overviewCallsAfter).toBe(overviewCallsBefore);
  });
});
