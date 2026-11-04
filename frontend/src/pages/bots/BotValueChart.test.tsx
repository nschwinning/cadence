import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { BotValueChart, buildBotValueOption, trendOf } from './BotValueChart';
import { apiClient } from '../../api/client';
import type { BotValuePoint } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

/** A daily end-of-day point for date `YYYY-MM-DD`. */
function dailyPoint(date: string, total: number): BotValuePoint {
  return {
    timestamp: `${date}T23:59:59Z`,
    total_value: total,
    realised_pnl: 0,
    unrealised_pnl: 0,
  };
}

/** An intraday point at a full ISO timestamp. */
function intradayPoint(timestamp: string, total: number): BotValuePoint {
  return { timestamp, total_value: total, realised_pnl: 0, unrealised_pnl: 0 };
}

function renderChart(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('trendOf', () => {
  it('reads the overall direction from first to last value', () => {
    expect(trendOf([dailyPoint('2026-01-04', 100), dailyPoint('2026-01-05', 110)])).toBe('up');
    expect(trendOf([dailyPoint('2026-01-04', 110), dailyPoint('2026-01-05', 100)])).toBe('down');
    expect(trendOf([dailyPoint('2026-01-04', 100), dailyPoint('2026-01-05', 100)])).toBe('flat');
  });
});

describe('buildBotValueOption', () => {
  it('draws a single value line coloured by its trend', () => {
    const series = (
      buildBotValueOption(
        [dailyPoint('2026-01-04', 10000), dailyPoint('2026-01-05', 11000)],
        { resolution: 'daily' },
      ).series ?? []
    ) as Array<Record<string, unknown>>;
    expect(series).toHaveLength(1);
    expect(series[0].id).toBe('value');
    expect((series[0].itemStyle as { color: string }).color).toBe('#059669');
  });

  it('carries the daily line flat to the horizon over a trailing weekend', () => {
    const series = (
      buildBotValueOption(
        [dailyPoint('2026-01-08', 10000), dailyPoint('2026-01-09', 10100)],
        { resolution: 'daily', horizon: '2026-01-11' },
      ).series ?? []
    ) as Array<{ id: string; data: [number, number | null][] }>;
    expect(series[0].data).toEqual([
      [Date.parse('2026-01-08'), 10000],
      [Date.parse('2026-01-09'), 10100],
      [Date.parse('2026-01-11'), 10100], // carried flat from Friday
    ]);
  });

  it('plots intraday points raw off their timestamps without carry-forward', () => {
    const series = (
      buildBotValueOption(
        [
          intradayPoint('2026-01-06T15:00:00Z', 10000),
          intradayPoint('2026-01-06T15:05:00Z', 10050),
        ],
        { resolution: '5min', horizon: '2026-01-11' },
      ).series ?? []
    ) as Array<{ data: [number, number][] }>;
    // No horizon point appended: exactly the two raw timestamps.
    expect(series[0].data).toEqual([
      [Date.parse('2026-01-06T15:00:00Z'), 10000],
      [Date.parse('2026-01-06T15:05:00Z'), 10050],
    ]);
  });
});

describe('BotValueChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the chart for at least two points', async () => {
    mockedGet.mockResolvedValue({
      data: {
        items: [dailyPoint('2026-01-04', 10000), dailyPoint('2026-01-05', 10100)],
        total: 2,
        resolution: 'daily',
      },
    });

    renderChart(<BotValueChart sessionId="b1" />);

    expect(
      await screen.findByRole('img', { name: /bot value over 2 daily points/i }),
    ).toBeInTheDocument();
  });

  it('shows the placeholder below two points', async () => {
    mockedGet.mockResolvedValue({
      data: { items: [dailyPoint('2026-01-04', 10000)], total: 1, resolution: 'daily' },
    });

    renderChart(<BotValueChart sessionId="b1" />);

    expect(
      await screen.findByText(/not enough history to chart yet/i),
    ).toBeInTheDocument();
  });

  it('refetches with the new resolution when the switcher changes', async () => {
    // Route the mock by the requested resolution param (default = daily).
    mockedGet.mockImplementation((_url: string, config?: { params?: { resolution?: string } }) => {
      const resolution = config?.params?.resolution ?? 'daily';
      return Promise.resolve({
        data: {
          items: [dailyPoint('2026-01-04', 10000), dailyPoint('2026-01-05', 10100)],
          total: 2,
          resolution,
        },
      });
    });
    const user = userEvent.setup();

    renderChart(<BotValueChart sessionId="b1" />);

    // Default load is daily.
    await screen.findByRole('img', { name: /daily points/i });

    await user.click(screen.getByRole('button', { name: '5m' }));

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith(
        expect.stringContaining('/value-history'),
        expect.objectContaining({ params: { resolution: '5min' } }),
      );
    });
    expect(screen.getByRole('button', { name: '5m' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});
