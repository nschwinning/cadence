import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { SessionValueChart } from './SessionValueChart';
import { apiClient } from '../../api/client';
import type { SessionValueSnapshot } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

function snapshot(date: string, total: number): SessionValueSnapshot {
  return {
    id: `snap-${date}`,
    session_id: 's1',
    snapshot_date: date,
    total_value: total,
    cash_value: total,
    positions_value: 0,
    daily_pnl: 0,
    daily_pnl_pct: 0,
    positions: [],
    created_at: `${date}T21:00:00Z`,
  };
}

function renderChart(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('SessionValueChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a polyline when there are at least two snapshots', async () => {
    mockedGet.mockResolvedValue({
      data: {
        items: [
          snapshot('2026-01-04', 100000),
          snapshot('2026-01-05', 100500),
          snapshot('2026-01-06', 101200),
        ],
        total: 3,
      },
    });

    const { container } = renderChart(<SessionValueChart sessionId="s1" />);

    const svg = await screen.findByRole('img', {
      name: /portfolio value over the last 3 daily snapshots/i,
    });
    expect(svg).toBeInTheDocument();
    const polyline = container.querySelector('polyline');
    expect(polyline).not.toBeNull();
    // Three points -> three "x,y" pairs.
    expect(polyline?.getAttribute('points')?.trim().split(' ')).toHaveLength(3);
  });

  it('shows the placeholder when there are fewer than two snapshots', async () => {
    mockedGet.mockResolvedValue({
      data: { items: [snapshot('2026-01-04', 100000)], total: 1 },
    });

    const { container } = renderChart(<SessionValueChart sessionId="s1" />);

    expect(
      await screen.findByText(/not enough history to chart yet/i),
    ).toBeInTheDocument();
    expect(container.querySelector('polyline')).toBeNull();
  });

  it('shows a loading state while the history is pending', () => {
    mockedGet.mockReturnValue(new Promise(() => {}));
    renderChart(<SessionValueChart sessionId="s1" />);
    expect(screen.getByRole('status')).toHaveTextContent(/loading/i);
  });

  it('shows an error state when the history request fails', async () => {
    mockedGet.mockRejectedValue(new Error('boom'));
    renderChart(<SessionValueChart sessionId="s1" />);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not load portfolio value/i,
    );
  });
});
