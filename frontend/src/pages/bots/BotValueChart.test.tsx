import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { BotValueChart, buildBotValueOption, trendOf } from './BotValueChart';
import { apiClient } from '../../api/client';
import type { BotValueSnapshot } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

function snapshot(date: string, total: number): BotValueSnapshot {
  return {
    snapshot_date: date,
    total_value: total,
    realised_pnl: 0,
    unrealised_pnl: 0,
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

describe('trendOf', () => {
  it('reads the overall direction from first to last value', () => {
    expect(trendOf([snapshot('2026-01-04', 100), snapshot('2026-01-05', 110)])).toBe('up');
    expect(trendOf([snapshot('2026-01-04', 110), snapshot('2026-01-05', 100)])).toBe('down');
    expect(trendOf([snapshot('2026-01-04', 100), snapshot('2026-01-05', 100)])).toBe('flat');
  });
});

describe('buildBotValueOption', () => {
  it('draws a single value line coloured by its trend', () => {
    const series = (
      buildBotValueOption([
        snapshot('2026-01-04', 10000),
        snapshot('2026-01-05', 11000),
      ]).series ?? []
    ) as Array<Record<string, unknown>>;
    expect(series).toHaveLength(1);
    expect(series[0].id).toBe('value');
    expect((series[0].itemStyle as { color: string }).color).toBe('#059669');
  });

  it('carries the value line flat to the horizon over a trailing weekend', () => {
    const series = (
      buildBotValueOption(
        [snapshot('2026-01-08', 10000), snapshot('2026-01-09', 10100)],
        '2026-01-11',
      ).series ?? []
    ) as Array<{ id: string; data: [number, number | null][] }>;
    expect(series[0].data).toEqual([
      [Date.parse('2026-01-08'), 10000],
      [Date.parse('2026-01-09'), 10100],
      [Date.parse('2026-01-11'), 10100], // carried flat from Friday
    ]);
  });
});

describe('BotValueChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the chart for at least two snapshots', async () => {
    mockedGet.mockResolvedValue({
      data: {
        items: [snapshot('2026-01-04', 10000), snapshot('2026-01-05', 10100)],
        total: 2,
      },
    });

    renderChart(<BotValueChart sessionId="b1" />);

    expect(
      await screen.findByRole('img', {
        name: /bot value over the last 2 daily snapshots/i,
      }),
    ).toBeInTheDocument();
  });

  it('shows the placeholder below two snapshots', async () => {
    mockedGet.mockResolvedValue({
      data: { items: [snapshot('2026-01-04', 10000)], total: 1 },
    });

    renderChart(<BotValueChart sessionId="b1" />);

    expect(
      await screen.findByText(/not enough history to chart yet/i),
    ).toBeInTheDocument();
  });
});
