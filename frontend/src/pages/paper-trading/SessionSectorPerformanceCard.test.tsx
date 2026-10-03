import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { SessionSectorPerformanceCard } from './SessionSectorPerformanceCard';
import { apiClient } from '../../api/client';
import type {
  SessionGroupPerformance,
  SessionSectorPerformance,
} from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

function group(
  key: string,
  overrides: Partial<SessionGroupPerformance> = {},
): SessionGroupPerformance {
  return {
    key,
    market_value: 0,
    realized_pnl: 0,
    unrealized_pnl: 0,
    total_pnl: 0,
    return_pct: null,
    ...overrides,
  };
}

function renderCard(data: SessionSectorPerformance | null) {
  if (data === null) {
    mockedGet.mockReturnValue(new Promise(() => {}));
  } else {
    mockedGet.mockResolvedValue({ data });
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactNode = <SessionSectorPerformanceCard sessionId="s-1" />;
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('SessionSectorPerformanceCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders signed P&L and return per sector group', async () => {
    renderCard({
      by_sector: [
        group('technology', {
          market_value: 5000,
          total_pnl: 1200,
          return_pct: 0.3,
        }),
        group('energy', {
          market_value: 2000,
          total_pnl: -400,
          return_pct: -0.1,
        }),
      ],
      by_category: [
        group('stock', { market_value: 7000, total_pnl: 800, return_pct: 0.12 }),
      ],
    });

    expect(await screen.findByText('technology')).toBeInTheDocument();
    const gain = screen.getByText('$1,200.00');
    expect(gain).toHaveClass('text-emerald-700');
    const loss = screen.getByText('-$400.00');
    expect(loss).toHaveClass('text-red-700');
    expect(screen.getByText('30.00%')).toHaveClass('text-emerald-700');
    expect(screen.getByText('-10.00%')).toHaveClass('text-red-700');
  });

  it('shows "Not available" for a group with a null return', async () => {
    renderCard({
      by_sector: [
        group('No sector', {
          market_value: 1000,
          total_pnl: 50,
          return_pct: null,
        }),
      ],
      by_category: [],
    });

    expect(await screen.findByText('No sector')).toBeInTheDocument();
    expect(screen.getByText('Not available')).toBeInTheDocument();
  });

  it('toggles between sector and category groupings', async () => {
    renderCard({
      by_sector: [group('technology', { total_pnl: 100, return_pct: 0.1 })],
      by_category: [group('crypto', { total_pnl: 200, return_pct: 0.2 })],
    });

    expect(await screen.findByText('technology')).toBeInTheDocument();
    expect(screen.queryByText('crypto')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'By category' }));

    expect(await screen.findByText('crypto')).toBeInTheDocument();
    expect(screen.queryByText('technology')).not.toBeInTheDocument();
  });

  it('renders an empty state when both groupings are empty', async () => {
    renderCard({ by_sector: [], by_category: [] });

    expect(
      await screen.findByText('No positions to attribute yet.'),
    ).toBeInTheDocument();
  });
});
