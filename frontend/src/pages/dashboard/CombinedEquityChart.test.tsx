import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CombinedEquityChart, buildCombinedOption } from './CombinedEquityChart';
import { makeSession } from './fixtures';
import type { DashboardBenchmarkSeries } from '../../types/api';

// Mock the ECharts wrapper so tests can inspect the option passed to it (the real
// SVG render is exercised elsewhere). Keeps the accessible `role="img"` name so the
// presence/empty-state assertions below still resolve the chart.
vi.mock('../../components/charts/EChart', () => ({
  EChart: ({
    option,
    ariaLabel,
  }: {
    option: unknown;
    ariaLabel?: string;
  }) => (
    <div role="img" aria-label={ariaLabel} data-option={JSON.stringify(option)} />
  ),
}));

/** Read the series array off the mocked chart's captured option. */
function chartSeries(): Array<{ id: string; data: Array<[number, number]> }> {
  const el = screen.getByRole('img', { name: /combined portfolio value/i });
  const option = JSON.parse(el.getAttribute('data-option') ?? '{}');
  return option.series ?? [];
}

const sessions = [
  makeSession({ id: 'a', label: 'Alpha' }),
  makeSession({ id: 'b', label: 'Beta' }),
];

/** The eight catalog indexes, with S&P 500 carrying a plottable price series. */
const benchmarkSeries: DashboardBenchmarkSeries[] = [
  {
    benchmark_id: 'SP500',
    name: 'S&P 500',
    points: [
      { date: '2026-06-01', price: 100 },
      { date: '2026-06-15', price: 110 },
    ],
  },
  { benchmark_id: 'DJIA', name: 'Dow Jones', points: [
    { date: '2026-06-01', price: 300 },
    { date: '2026-06-15', price: 306 },
  ] },
  { benchmark_id: 'NYSE_COMPOSITE', name: 'NYSE Composite', points: [] },
  { benchmark_id: 'NASDAQ_COMPOSITE', name: 'Nasdaq Composite', points: [] },
  { benchmark_id: 'NASDAQ_100', name: 'Nasdaq 100', points: [] },
  { benchmark_id: 'RUSSELL_2000', name: 'Russell 2000', points: [] },
  { benchmark_id: 'SP100', name: 'S&P 100', points: [] },
  { benchmark_id: 'WILSHIRE_5000', name: 'Wilshire 5000', points: [] },
];

describe('buildCombinedOption', () => {
  const points = [
    { date: '2026-06-01', value: 20000 },
    { date: '2026-06-15', value: 22000 },
  ];

  it('plots a single emerald combined-value line', () => {
    const series = (buildCombinedOption(points).series ?? []) as Array<
      Record<string, unknown>
    >;
    expect(series).toHaveLength(1);
    expect(series[0].id).toBe('combined');
    expect((series[0].itemStyle as { color: string }).color).toBe('#059669');
    expect(series[0].data).toEqual([
      [Date.parse('2026-06-01'), 20000],
      [Date.parse('2026-06-15'), 22000],
    ]);
  });

  it('formats the y-axis in USD on a scaled (non-zero) domain', () => {
    const yAxis = buildCombinedOption(points).yAxis as {
      scale: boolean;
      axisLabel: { formatter: (v: number) => string };
    };
    expect(yAxis.scale).toBe(true);
    expect(yAxis.axisLabel.formatter(22000)).toBe('$22,000.00');
  });

  it('uses a shared time x-axis with a German dated formatter', () => {
    const xAxis = buildCombinedOption(points).xAxis as {
      type: string;
      axisLabel: { formatter: (v: number) => string };
    };
    expect(xAxis.type).toBe('time');
    expect(xAxis.axisLabel.formatter(Date.parse('2026-06-01'))).toBe('01.06');
  });

  it('builds a tooltip reporting the combined value at the hovered date', () => {
    const formatter = (
      buildCombinedOption(points).tooltip as {
        formatter: (p: unknown) => string;
      }
    ).formatter;
    const ts = Date.parse('2026-06-15');
    const html = formatter([
      { axisValue: ts, seriesName: 'Combined value', value: [ts, 22000], marker: '' },
    ]);
    expect(html).toContain('15.06.2026');
    expect(html).toContain('Combined value');
    expect(html).toContain('$22,000.00');
  });

  it('adds a dashed benchmark line from the aggregated dollar points', () => {
    const benchmarkLines = [
      {
        id: 'SP500',
        name: 'S&P 500',
        color: '#64748b',
        points: [
          { date: '2026-06-01', value: 20000 }, // aggregated dollar value
          { date: '2026-06-15', value: 22000 },
        ],
      },
    ];
    const series = (buildCombinedOption(points, benchmarkLines).series ??
      []) as Array<Record<string, unknown>>;
    expect(series).toHaveLength(2);
    const bench = series[1];
    expect(bench.id).toBe('benchmark:SP500');
    expect(bench.name).toBe('S&P 500');
    expect((bench.lineStyle as { type: string }).type).toBe('dashed');
    // Plots the aggregated dollar points verbatim on the time axis.
    expect((bench.data as Array<[number, number]>)[0]).toEqual([
      Date.parse('2026-06-01'),
      20000,
    ]);
  });

  it('reports each drawn benchmark value in the tooltip', () => {
    const benchmarkLines = [
      {
        id: 'SP500',
        name: 'S&P 500',
        color: '#64748b',
        points: [
          { date: '2026-06-01', value: 20000 },
          { date: '2026-06-15', value: 22000 },
        ],
      },
    ];
    const formatter = (
      buildCombinedOption(points, benchmarkLines).tooltip as {
        formatter: (p: unknown) => string;
      }
    ).formatter;
    const ts = Date.parse('2026-06-15');
    const html = formatter([
      { axisValue: ts, seriesName: 'Combined value', value: [ts, 22000], marker: '' },
      { axisValue: ts, seriesName: 'S&P 500', value: [ts, 22000], marker: '' },
    ]);
    expect(html).toContain('15.06.2026');
    expect(html).toContain('S&P 500');
    expect(html).toContain('$22,000.00');
  });
});

describe('CombinedEquityChart', () => {
  it('draws the chart when sessions are selected', () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a', 'b'])}
        onToggle={() => {}}
        benchmarkSeries={benchmarkSeries}
      />,
    );
    expect(
      screen.getByRole('img', { name: /combined portfolio value/i }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('equity-empty')).not.toBeInTheDocument();
  });

  it('shows the empty state when nothing is selected', () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set()}
        onToggle={() => {}}
        benchmarkSeries={benchmarkSeries}
      />,
    );
    expect(screen.getByTestId('equity-empty')).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: /combined portfolio value/i }),
    ).not.toBeInTheDocument();
  });

  it('shows the placeholder when the selection has too little history to plot', () => {
    const single = [
      makeSession({ id: 'a', label: 'Alpha', points: [{ date: '2026-06-01', value: 10000 }] }),
    ];
    render(
      <CombinedEquityChart
        sessions={single}
        selectedIds={new Set(['a'])}
        onToggle={() => {}}
        benchmarkSeries={benchmarkSeries}
      />,
    );
    expect(screen.getByTestId('equity-placeholder')).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: /combined portfolio value/i }),
    ).not.toBeInTheDocument();
  });

  it('toggles a session via its legend checkbox', async () => {
    const onToggle = vi.fn();
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a', 'b'])}
        onToggle={onToggle}
        benchmarkSeries={benchmarkSeries}
      />,
    );
    await userEvent.click(screen.getByRole('checkbox', { name: /Beta/ }));
    expect(onToggle).toHaveBeenCalledWith('b');
  });

  it('lists every catalog benchmark with only S&P 500 checked by default', () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a', 'b'])}
        onToggle={() => {}}
        benchmarkSeries={benchmarkSeries}
      />,
    );
    const list = screen.getByRole('list', { name: /benchmark indexes/i });
    for (const bench of benchmarkSeries) {
      expect(screen.getByRole('checkbox', { name: bench.name })).toBeInTheDocument();
    }
    // Only S&P 500 is drawn by default.
    const sp500 = screen.getByRole('checkbox', { name: 'S&P 500' });
    expect(sp500).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Dow Jones' })).not.toBeChecked();
    expect(list).toBeInTheDocument();
  });

  it('disables a benchmark whose series has no points over the range', () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a', 'b'])}
        onToggle={() => {}}
        benchmarkSeries={benchmarkSeries}
      />,
    );
    // NYSE Composite has an empty series → inert, not an error.
    expect(screen.getByRole('checkbox', { name: 'NYSE Composite' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'S&P 500' })).toBeEnabled();
  });

  it('toggles a benchmark overlay locally without any refetch', async () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a', 'b'])}
        onToggle={() => {}}
        benchmarkSeries={benchmarkSeries}
      />,
    );
    const sp500 = screen.getByRole('checkbox', { name: 'S&P 500' });
    expect(sp500).toBeChecked();
    await userEvent.click(sp500);
    expect(sp500).not.toBeChecked();

    const djia = screen.getByRole('checkbox', { name: 'Dow Jones' });
    expect(djia).not.toBeChecked();
    await userEvent.click(djia);
    expect(djia).toBeChecked();
  });

  it('renders no benchmark legend in the empty state when no series are provided', () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set()}
        onToggle={() => {}}
        benchmarkSeries={[]}
      />,
    );
    expect(
      screen.queryByRole('list', { name: /benchmark indexes/i }),
    ).not.toBeInTheDocument();
  });

  it('draws the default S&P 500 line as the aggregated per-session buy-and-hold', () => {
    // Two sessions opening on different dates against a flat-priced index: a single
    // rebased curve would stay flat, but the aggregated buy-and-hold must step up on
    // the second session's open date — proving per-session aggregation, not rebasing.
    const a = makeSession({
      id: 'a',
      label: 'Alpha',
      points: [
        { date: '2026-06-01', value: 10000 },
        { date: '2026-06-10', value: 10000 },
      ],
      contributions: [{ effective_date: '2026-06-01', amount: 10000 }],
    });
    const b = makeSession({
      id: 'b',
      label: 'Beta',
      points: [
        { date: '2026-06-05', value: 10000 },
        { date: '2026-06-10', value: 10000 },
      ],
      contributions: [{ effective_date: '2026-06-05', amount: 10000 }],
    });
    const flatIndex: DashboardBenchmarkSeries[] = [
      {
        benchmark_id: 'SP500',
        name: 'S&P 500',
        points: [
          { date: '2026-06-01', price: 100 },
          { date: '2026-06-05', price: 100 },
          { date: '2026-06-10', price: 100 },
        ],
      },
    ];
    render(
      <CombinedEquityChart
        sessions={[a, b]}
        selectedIds={new Set(['a', 'b'])}
        onToggle={() => {}}
        benchmarkSeries={flatIndex}
      />,
    );
    const bench = chartSeries().find((s) => s.id === 'benchmark:SP500');
    expect(bench).toBeDefined();
    // 100 units @ 06-01, +100 units @ 06-05; flat price 100 → dollars step up.
    expect(bench?.data).toEqual([
      [Date.parse('2026-06-01'), 10000],
      [Date.parse('2026-06-05'), 20000], // steps up on Beta's open, not flat
      [Date.parse('2026-06-10'), 20000],
    ]);
  });

  it('sums the benchmark across exactly the selected sessions (no refetch on toggle)', () => {
    // Both sessions selected: each contributes 100 units @ price 100/110.
    const { rerender } = render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a', 'b'])}
        onToggle={() => {}}
        benchmarkSeries={benchmarkSeries}
      />,
    );
    const bothBench = chartSeries().find((s) => s.id === 'benchmark:SP500');
    const bothEquity = chartSeries().find((s) => s.id === 'combined');
    expect(bothBench?.data.at(-1)).toEqual([Date.parse('2026-06-15'), 22000]);
    expect(bothEquity?.data.at(-1)).toEqual([Date.parse('2026-06-15'), 22000]);

    // Toggling Beta off drops both the equity and benchmark lines by Beta's share,
    // recomputed from the already-fetched data (the same prop set, new selection).
    rerender(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a'])}
        onToggle={() => {}}
        benchmarkSeries={benchmarkSeries}
      />,
    );
    const oneBench = chartSeries().find((s) => s.id === 'benchmark:SP500');
    const oneEquity = chartSeries().find((s) => s.id === 'combined');
    expect(oneBench?.data.at(-1)).toEqual([Date.parse('2026-06-15'), 11000]);
    expect(oneEquity?.data.at(-1)).toEqual([Date.parse('2026-06-15'), 11000]);
  });
});
