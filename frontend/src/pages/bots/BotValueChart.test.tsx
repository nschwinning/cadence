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
    const option = buildBotValueOption(
      [dailyPoint('2026-01-08', 10000), dailyPoint('2026-01-09', 10100)],
      { resolution: 'daily', horizon: '2026-01-11' },
    ) as {
      xAxis: { type: string; data: string[] };
      series: Array<{ id: string; data: (number | null)[] }>;
    };
    // Category axis: one label per period, values aligned to those categories.
    expect(option.xAxis.type).toBe('category');
    expect(option.xAxis.data).toEqual(['08.01', '09.01', '11.01']);
    expect(option.series[0].data).toEqual([10000, 10100, 10100]); // carried flat
  });

  it('shows exactly one daily category per consecutive date with its own value', () => {
    const option = buildBotValueOption(
      [dailyPoint('2026-11-03', 10000), dailyPoint('2026-11-04', 10200)],
      { resolution: 'daily', horizon: '2026-11-04' },
    ) as {
      xAxis: { type: string; data: string[] };
      series: Array<{ data: (number | null)[] }>;
    };
    // No repeated date label and no neighbour-day value bleed.
    expect(option.xAxis.type).toBe('category');
    expect(option.xAxis.data).toEqual(['03.11', '04.11']);
    expect(new Set(option.xAxis.data).size).toBe(option.xAxis.data.length);
    expect(option.series[0].data).toEqual([10000, 10200]);
  });

  it('shows one monthly category per calendar month', () => {
    // Backend hands monthly as one point per month; the axis keeps one label each.
    const option = buildBotValueOption(
      [dailyPoint('2026-09-30', 10000), dailyPoint('2026-10-31', 10500)],
      { resolution: 'monthly', horizon: '2026-10-31' },
    ) as {
      xAxis: { type: string; data: string[] };
      series: Array<{ data: (number | null)[] }>;
    };
    expect(option.xAxis.type).toBe('category');
    expect(option.xAxis.data).toEqual(['30.09', '31.10']);
    expect(option.series[0].data).toEqual([10000, 10500]);
  });

  it('labels intraday axis ticks and tooltips in the local timezone', () => {
    const ms = Date.parse('2026-01-06T15:05:00Z');
    const option = buildBotValueOption(
      [intradayPoint('2026-01-06T15:05:00Z', 10000)],
      { resolution: '5min' },
    ) as {
      xAxis: { axisLabel: { formatter: (v: number) => string } };
      tooltip: { formatter: (p: unknown) => string };
    };

    // Expected labels derived from the same Date via LOCAL getters, so the test
    // passes in any CI timezone.
    const d = new Date(ms);
    const p2 = (n: number) => String(n).padStart(2, '0');
    const expectedAxis = `${p2(d.getDate())}.${p2(d.getMonth() + 1)} ${p2(d.getHours())}:${p2(d.getMinutes())}`;
    const expectedTooltip = `${p2(d.getDate())}.${p2(d.getMonth() + 1)}.${d.getFullYear()} ${p2(d.getHours())}:${p2(d.getMinutes())}`;

    const axisLabel = option.xAxis.axisLabel.formatter(ms);
    const tooltip = option.tooltip.formatter([
      { axisValue: ms, value: [ms, 10000] },
    ]);

    expect(axisLabel).toBe(expectedAxis);
    expect(tooltip).toContain(expectedTooltip);

    // When local time differs from UTC, the label must NOT be the UTC clock value.
    if (d.getTimezoneOffset() !== 0) {
      expect(axisLabel).not.toBe('06.01 15:05'); // UTC-sliced form
    }
  });

  it('labels daily ticks by calendar date with no clock-time or day shift', () => {
    const option = buildBotValueOption(
      [dailyPoint('2026-01-06', 10000), dailyPoint('2026-01-07', 10100)],
      { resolution: 'daily' },
    ) as { xAxis: { data: string[] } };

    // Category labels are date-only (no HH:mm), on the correct calendar day — and
    // derived from the ISO date parts so they never shift under a viewer's zone.
    expect(option.xAxis.data).toEqual(['06.01', '07.01']);
    option.xAxis.data.forEach((label) => expect(label).not.toMatch(/\d{2}:\d{2}/));
  });

  it('reads the daily tooltip date from the hovered category, not an epoch', () => {
    const option = buildBotValueOption(
      [dailyPoint('2026-11-03', 10000), dailyPoint('2026-11-04', 10200)],
      { resolution: 'daily', horizon: '2026-11-04' },
    ) as { tooltip: { formatter: (p: unknown) => string } };

    const tooltip = option.tooltip.formatter([{ dataIndex: 1, value: 10200 }]);
    expect(tooltip).toContain('04.11.2026');
    expect(tooltip).toContain('Bot value');
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
        items: [
          intradayPoint('2026-01-06T15:00:00Z', 10000),
          intradayPoint('2026-01-06T15:05:00Z', 10100),
        ],
        total: 2,
        resolution: '5min',
      },
    });

    renderChart(<BotValueChart sessionId="b1" />);

    // The chart opens at the 5-minute intraday resolution by default.
    expect(
      await screen.findByRole('img', { name: /bot value over 2 5min points/i }),
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

  it('defaults to 5m and refetches with the new resolution when the switcher changes', async () => {
    // Route the mock by the requested resolution param (default = 5min).
    mockedGet.mockImplementation((_url: string, config?: { params?: { resolution?: string } }) => {
      const resolution = config?.params?.resolution ?? '5min';
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

    // Default load is the 5-minute intraday resolution.
    await screen.findByRole('img', { name: /5min points/i });
    expect(mockedGet).toHaveBeenCalledWith(
      expect.stringContaining('/value-history'),
      expect.objectContaining({ params: { resolution: '5min' } }),
    );
    expect(screen.getByRole('button', { name: '5m' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    await user.click(screen.getByRole('button', { name: '1D' }));

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith(
        expect.stringContaining('/value-history'),
        expect.objectContaining({ params: { resolution: 'daily' } }),
      );
    });
    expect(screen.getByRole('button', { name: '1D' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('marks the badge intraday for 5m by default and end-of-day for coarse resolutions', async () => {
    mockedGet.mockImplementation((_url: string, config?: { params?: { resolution?: string } }) => {
      const resolution = config?.params?.resolution ?? '5min';
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

    // Default 5-minute resolution reads per-tick intraday points.
    await screen.findByRole('img', { name: /5min points/i });
    expect(screen.getByTestId('freshness-intraday')).toHaveTextContent(/intraday/i);
    expect(screen.queryByTestId('freshness-eod')).not.toBeInTheDocument();

    // Switching to a coarse resolution flips the badge to "End of day".
    await user.click(screen.getByRole('button', { name: '1D' }));
    expect(await screen.findByTestId('freshness-eod')).toHaveTextContent(/end of day/i);
    expect(screen.queryByTestId('freshness-intraday')).not.toBeInTheDocument();
    // Wait for the daily load to settle so the switcher is back on screen.
    await screen.findByRole('img', { name: /daily points/i });

    // Switching back to an intraday resolution restores the intraday marker.
    await user.click(screen.getByRole('button', { name: '5m' }));
    expect(await screen.findByTestId('freshness-intraday')).toHaveTextContent(/intraday/i);
    expect(screen.queryByTestId('freshness-eod')).not.toBeInTheDocument();
  });
});
