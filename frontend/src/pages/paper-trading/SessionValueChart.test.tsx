import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import {
  SessionValueChart,
  buildValueOption,
  trendOf,
  benchmarkDrawnFor,
} from './SessionValueChart';
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

/** Pull the plotted `series` array out of a built ECharts option. */
function optionSeries(snapshots: SessionValueSnapshot[]) {
  return (buildValueOption(snapshots).series ?? []) as Array<
    Record<string, unknown>
  >;
}

describe('trendOf', () => {
  it('reads the overall direction from first to last value', () => {
    expect(
      trendOf([snapshot('2026-01-04', 100), snapshot('2026-01-05', 110)]),
    ).toBe('up');
    expect(
      trendOf([snapshot('2026-01-04', 110), snapshot('2026-01-05', 100)]),
    ).toBe('down');
    expect(
      trendOf([snapshot('2026-01-04', 100), snapshot('2026-01-05', 100)]),
    ).toBe('flat');
  });
});

describe('benchmarkDrawnFor', () => {
  it('is true only with at least two non-null benchmark points', () => {
    expect(
      benchmarkDrawnFor([
        snapshot('2026-01-04', 100, 100),
        snapshot('2026-01-05', 110, 101),
      ]),
    ).toBe(true);
    expect(
      benchmarkDrawnFor([
        snapshot('2026-01-04', 100, 100),
        snapshot('2026-01-05', 110, null),
      ]),
    ).toBe(false);
    expect(
      benchmarkDrawnFor([
        snapshot('2026-01-04', 100),
        snapshot('2026-01-05', 110),
      ]),
    ).toBe(false);
  });
});

describe('buildValueOption', () => {
  it('colours the portfolio line by its trend', () => {
    const up = optionSeries([
      snapshot('2026-01-04', 100000),
      snapshot('2026-01-05', 110000),
    ]);
    expect((up[0].itemStyle as { color: string }).color).toBe('#059669');
    const down = optionSeries([
      snapshot('2026-01-04', 110000),
      snapshot('2026-01-05', 100000),
    ]);
    expect((down[0].itemStyle as { color: string }).color).toBe('#dc2626');
  });

  it('adds the benchmark overlay only when it has enough points', () => {
    const withBenchmark = optionSeries([
      snapshot('2026-01-04', 100000, 100000),
      snapshot('2026-01-05', 110000, 101000),
    ]);
    expect(withBenchmark).toHaveLength(2);
    expect(withBenchmark[1].id).toBe('benchmark');

    const withoutBenchmark = optionSeries([
      snapshot('2026-01-04', 100000),
      snapshot('2026-01-05', 110000),
    ]);
    expect(withoutBenchmark).toHaveLength(1);
    expect(withoutBenchmark[0].id).toBe('portfolio');
  });

  it('formats the y-axis in USD on a scaled (non-zero) domain', () => {
    const opt = buildValueOption([
      snapshot('2026-01-04', 100000),
      snapshot('2026-01-05', 110000),
    ]);
    const yAxis = opt.yAxis as {
      scale: boolean;
      axisLabel: { formatter: (v: number) => string };
    };
    expect(yAxis.scale).toBe(true);
    expect(yAxis.axisLabel.formatter(110000)).toBe('$110,000.00');
  });

  it('uses a shared time x-axis with a dated formatter', () => {
    const xAxis = buildValueOption([
      snapshot('2026-01-04', 100000),
      snapshot('2026-01-05', 110000),
    ]).xAxis as { type: string; axisLabel: { formatter: (v: number) => string } };
    expect(xAxis.type).toBe('time');
    expect(xAxis.axisLabel.formatter(Date.parse('2026-01-04'))).toBe('04.01');
  });

  it('builds a tooltip reporting each line, skipping a null benchmark row', () => {
    const opt = buildValueOption([
      snapshot('2026-01-04', 100000, 100000),
      snapshot('2026-01-05', 110000, 101000),
    ]);
    const formatter = (opt.tooltip as { formatter: (p: unknown) => string })
      .formatter;
    const ts = Date.parse('2026-01-05');
    expect(
      formatter([
        { axisValue: ts, seriesName: 'Portfolio value', value: [ts, 110000], marker: '' },
        { axisValue: ts, seriesName: 'Benchmark', value: [ts, 101000], marker: '' },
      ]),
    ).toContain('$101,000.00');
    // A row whose benchmark value is null is dropped from the tooltip.
    const withNull = formatter([
      { axisValue: ts, seriesName: 'Portfolio value', value: [ts, 110000], marker: '' },
      { axisValue: ts, seriesName: 'Benchmark', value: [ts, null], marker: '' },
    ]);
    expect(withNull).toContain('05.01.2026');
    expect(withNull).toContain('Portfolio value');
    expect(withNull).not.toContain('Benchmark');
  });
});

describe('SessionValueChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the chart for at least two snapshots', async () => {
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

    expect(
      await screen.findByRole('img', {
        name: /portfolio value over the last 3 daily snapshots/i,
      }),
    ).toBeInTheDocument();
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
    expect(within(legend).getByTestId('benchmark-legend')).toBeInTheDocument();
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

  it('shows the placeholder without a chart or legend below two snapshots', async () => {
    mockedGet.mockResolvedValue({
      data: { items: [snapshot('2026-01-04', 100000)], total: 1 },
    });

    renderChart(<SessionValueChart sessionId="s1" />);

    expect(
      await screen.findByText(/not enough history to chart yet/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /portfolio value over/i })).toBeNull();
    expect(screen.queryByTestId('value-legend')).not.toBeInTheDocument();
  });

  it('marks the chart as end-of-day with an explanatory hint', async () => {
    mockedGet.mockResolvedValue({
      data: {
        items: [snapshot('2026-01-04', 100000), snapshot('2026-01-05', 100500)],
        total: 2,
      },
    });

    renderChart(<SessionValueChart sessionId="s1" />);

    const badge = await screen.findByTestId('freshness-eod');
    expect(badge).toHaveTextContent(/end of day/i);
    expect(badge).toHaveAttribute('title', expect.stringMatching(/lag the live/i));
  });

  it('shows the end-of-day badge even in the not-enough-history placeholder state', async () => {
    mockedGet.mockResolvedValue({
      data: { items: [snapshot('2026-01-04', 100000)], total: 1 },
    });

    renderChart(<SessionValueChart sessionId="s1" />);

    expect(
      await screen.findByText(/not enough history to chart yet/i),
    ).toBeInTheDocument();
    expect(screen.getByTestId('freshness-eod')).toHaveTextContent(/end of day/i);
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
