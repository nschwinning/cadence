import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { SessionValueChart } from './SessionValueChart';
import { apiClient } from '../../api/client';
import type { SessionValueSnapshot } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

function snapshot(
  date: string,
  total: number,
  benchmarkValue: number | null = null,
): SessionValueSnapshot {
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
    benchmark_value: benchmarkValue,
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

  it('renders the benchmark overlay line when benchmark values are present', async () => {
    mockedGet.mockResolvedValue({
      data: {
        items: [
          snapshot('2026-01-04', 100000, 100000),
          snapshot('2026-01-05', 100500, 100200),
          snapshot('2026-01-06', 101200, 100900),
        ],
        total: 3,
      },
    });

    const { container } = renderChart(<SessionValueChart sessionId="s1" />);

    await screen.findByRole('img', {
      name: /portfolio value over the last 3 daily snapshots/i,
    });
    expect(container.querySelector('[data-testid="benchmark-line"]')).not.toBeNull();
  });

  it('omits the benchmark overlay line when all benchmark values are null', async () => {
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

    await screen.findByRole('img', {
      name: /portfolio value over the last 3 daily snapshots/i,
    });
    expect(container.querySelector('[data-testid="benchmark-line"]')).toBeNull();
  });

  it('labels the x-axis with dates and the y-axis with USD', async () => {
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

    renderChart(<SessionValueChart sessionId="s1" />);

    await screen.findByRole('img', {
      name: /portfolio value over the last 3 daily snapshots/i,
    });
    // Y-axis shows the max value in USD; x-axis shows the first and last date.
    const yLabels = screen.getAllByTestId('chart-y-label');
    expect(yLabels[0]).toHaveTextContent('$101,200.00');
    const xLabels = screen.getAllByTestId('chart-x-label');
    expect(xLabels.map((el) => el.textContent)).toEqual(['1/4', '1/6']);
  });

  it('names both lines in the legend when the benchmark is drawn', async () => {
    mockedGet.mockResolvedValue({
      data: {
        items: [
          snapshot('2026-01-04', 100000, 100000),
          snapshot('2026-01-05', 100500, 100200),
        ],
        total: 2,
      },
    });

    renderChart(<SessionValueChart sessionId="s1" />);

    const legend = await screen.findByTestId('value-legend');
    expect(within(legend).getByText('Portfolio value')).toBeInTheDocument();
    expect(within(legend).getByText('Benchmark')).toBeInTheDocument();
  });

  it('names only the portfolio line when the benchmark is absent', async () => {
    mockedGet.mockResolvedValue({
      data: {
        items: [snapshot('2026-01-04', 100000), snapshot('2026-01-05', 100500)],
        total: 2,
      },
    });

    renderChart(<SessionValueChart sessionId="s1" />);

    const legend = await screen.findByTestId('value-legend');
    expect(within(legend).getByText('Portfolio value')).toBeInTheDocument();
    expect(within(legend).queryByText('Benchmark')).not.toBeInTheDocument();
  });

  it('shows the placeholder without axes or a legend below two snapshots', async () => {
    mockedGet.mockResolvedValue({
      data: { items: [snapshot('2026-01-04', 100000)], total: 1 },
    });

    const { container } = renderChart(<SessionValueChart sessionId="s1" />);

    expect(
      await screen.findByText(/not enough history to chart yet/i),
    ).toBeInTheDocument();
    expect(container.querySelector('polyline')).toBeNull();
    expect(screen.queryByTestId('chart-axes')).not.toBeInTheDocument();
    expect(screen.queryByTestId('value-legend')).not.toBeInTheDocument();
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
