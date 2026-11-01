import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  SessionComparisonChart,
  buildComparisonSeries,
  buildComparisonOption,
  type Metric,
} from './SessionComparisonChart';
import { apiClient } from '../../api/client';
import { CATEGORICAL_PALETTE, categoricalColor } from '../../lib/palette';
import type { SessionValueComparisonSeries } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

// Mock the ECharts wrapper so the weekend carry-forward test can inspect the
// option (its series data) passed to it; keeps the accessible role="img" name.
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

// Pin "today" (the carry-forward horizon) so plotted data is deterministic.
vi.mock('../../lib/carryForward', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../lib/carryForward')>();
  return { ...actual, todayEt: () => '2026-01-11' };
});

const mockedGet = vi.mocked(apiClient.get);

function series(
  id: string,
  label: string,
  capital: number,
  pts: [string, number][],
): SessionValueComparisonSeries {
  return {
    session_id: id,
    label,
    allocated_capital: capital,
    points: pts.map(([snapshot_date, total_value]) => ({
      snapshot_date,
      total_value,
    })),
  };
}

function renderChart(sessions: SessionValueComparisonSeries[] | null) {
  if (sessions === null) {
    mockedGet.mockReturnValue(new Promise(() => {}));
  } else {
    mockedGet.mockResolvedValue({ data: { sessions } });
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SessionComparisonChart />
    </QueryClientProvider>,
  );
}

/** Pull the plotted `series` array out of a built ECharts option. */
function optionSeries(metric: Metric, data: SessionValueComparisonSeries[]) {
  const built = buildComparisonOption(buildComparisonSeries(data, metric), metric);
  return (built.series ?? []) as Array<Record<string, unknown>>;
}

describe('buildComparisonSeries', () => {
  it('normalises points to return fraction in the return metric', () => {
    const [s] = buildComparisonSeries(
      [series('a', 'Alpha', 100000, [['2026-01-04', 100000], ['2026-01-05', 110000]])],
      'return',
    );
    expect(s.points.map((p) => p.value)).toEqual([0, 0.1]);
  });

  it('uses raw total value in the value metric', () => {
    const [s] = buildComparisonSeries(
      [series('a', 'Alpha', 100000, [['2026-01-04', 100000], ['2026-01-05', 110000]])],
      'value',
    );
    expect(s.points.map((p) => p.value)).toEqual([100000, 110000]);
  });

  it('drops a session to legend-only when capital is non-positive in the return view', () => {
    const [s] = buildComparisonSeries(
      [series('a', 'Alpha', 0, [['2026-01-04', 100], ['2026-01-05', 110]])],
      'return',
    );
    expect(s.points).toHaveLength(0);
  });

  it('assigns a distinct colour per session by position, never colliding within the palette', () => {
    // One session per palette colour: every assigned colour must be unique.
    const many = Array.from({ length: CATEGORICAL_PALETTE.length }, (_, i) =>
      series(`s${i}`, `S${i}`, 100000, [
        ['2026-01-04', 100000],
        ['2026-01-05', 101000],
      ]),
    );
    const colors = buildComparisonSeries(many, 'return').map((s) => s.color);
    expect(colors).toEqual([...CATEGORICAL_PALETTE]);
    expect(new Set(colors).size).toBe(colors.length);
    // Colour follows list position (oldest-created first from the API).
    const [first, second] = buildComparisonSeries(
      [many[0], many[1]],
      'return',
    );
    expect(first.color).toBe(categoricalColor(0));
    expect(second.color).toBe(categoricalColor(1));
  });

  it('preserves the input order (which the API returns oldest-created first)', () => {
    const list = buildComparisonSeries(
      [
        series('old', 'Old', 100000, [['2026-01-04', 100000], ['2026-01-05', 101000]]),
        series('new', 'New', 100000, [['2026-01-04', 100000], ['2026-01-05', 102000]]),
      ],
      'return',
    );
    expect(list.map((s) => s.id)).toEqual(['old', 'new']);
  });
});

describe('buildComparisonOption', () => {
  it('plots only sessions with at least two points', () => {
    const plotted = optionSeries('return', [
      series('a', 'Alpha', 100000, [['2026-01-04', 100000], ['2026-01-05', 101000]]),
      series('b', 'Beta', 100000, [['2026-01-04', 100000]]),
    ]);
    expect(plotted).toHaveLength(1);
    expect(plotted[0].name).toBe('Alpha');
  });

  it('adds a 0 baseline mark-line in the return view and omits it in the value view', () => {
    const data = [
      series('a', 'Alpha', 100000, [['2026-01-04', 100000], ['2026-01-05', 110000]]),
    ];
    expect(optionSeries('return', data)[0].markLine).toBeDefined();
    expect(optionSeries('value', data)[0].markLine).toBeUndefined();
  });

  it('formats the y-axis for the active metric', () => {
    const data = [
      series('a', 'Alpha', 100000, [['2026-01-04', 100000], ['2026-01-05', 110000]]),
    ];
    const returnOpt = buildComparisonOption(
      buildComparisonSeries(data, 'return'),
      'return',
    );
    const valueOpt = buildComparisonOption(
      buildComparisonSeries(data, 'value'),
      'value',
    );
    const yFmt = (opt: typeof returnOpt) =>
      (opt.yAxis as { axisLabel: { formatter: (v: number) => string } }).axisLabel
        .formatter;
    expect(yFmt(returnOpt)(0.1)).toBe('10.00%');
    expect(yFmt(valueOpt)(110000)).toBe('$110,000.00');
  });

  it('builds a tooltip reporting the date and each series label + formatted value', () => {
    const data = [
      series('a', 'Alpha', 100000, [['2026-01-04', 100000], ['2026-01-05', 110000]]),
    ];
    const opt = buildComparisonOption(buildComparisonSeries(data, 'return'), 'return');
    const formatter = (
      opt.tooltip as { formatter: (p: unknown) => string }
    ).formatter;
    const html = formatter([
      {
        axisValue: Date.parse('2026-01-05'),
        seriesName: 'Alpha',
        value: [Date.parse('2026-01-05'), 0.1],
        marker: '',
      },
    ]);
    expect(html).toContain('05.01.2026');
    expect(html).toContain('Alpha');
    expect(html).toContain('10.00%');
  });

  it('uses a shared time x-axis with a dated formatter', () => {
    const opt = buildComparisonOption(
      buildComparisonSeries(
        [series('a', 'Alpha', 100000, [['2026-01-04', 100000], ['2026-01-05', 110000]])],
        'return',
      ),
      'return',
    );
    const xAxis = opt.xAxis as {
      type: string;
      axisLabel: { formatter: (v: number) => string };
    };
    expect(xAxis.type).toBe('time');
    expect(xAxis.axisLabel.formatter(Date.parse('2026-01-04'))).toBe('04.01');
  });
});

describe('SessionComparisonChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the chart and a legend for plottable sessions, defaulting to return %', async () => {
    renderChart([
      series('a', 'Alpha', 100000, [['2026-01-04', 100000], ['2026-01-05', 110000]]),
      series('b', 'Beta', 50000, [['2026-01-04', 50000], ['2026-01-05', 52000]]),
    ]);

    await screen.findByRole('img', { name: /return percent/i });
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
    // Default is the return metric: +10% shows in Alpha's legend summary.
    expect(screen.getByText(/· 10\.00%/)).toBeInTheDocument();
  });

  it('toggles between the return % and value $ metrics', async () => {
    renderChart([
      series('a', 'Alpha', 100000, [['2026-01-04', 100000], ['2026-01-05', 110000]]),
    ]);

    await screen.findByRole('img', { name: /return percent/i });
    expect(screen.getByText(/· 10\.00%/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Value $' }));

    expect(
      screen.getByRole('img', { name: /portfolio value/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/· \$110,000\.00/)).toBeInTheDocument();
  });

  it('legends but does not plot a session with fewer than two points', async () => {
    renderChart([
      series('a', 'Alpha', 100000, [['2026-01-04', 100000], ['2026-01-05', 101000]]),
      series('b', 'Beta', 100000, [['2026-01-04', 100000]]),
    ]);

    await screen.findByRole('img', { name: /return percent/i });
    expect(screen.getByText('Beta')).toBeInTheDocument();
    expect(screen.getByText(/no chart data/i)).toBeInTheDocument();
  });

  it('shows the placeholder when no session has enough points', async () => {
    renderChart([series('a', 'Alpha', 100000, [['2026-01-04', 100000]])]);

    expect(
      await screen.findByTestId('comparison-placeholder'),
    ).toHaveTextContent(/not enough history to compare yet/i);
    expect(screen.queryByRole('img', { name: /return percent/i })).toBeNull();
  });

  it('shows a loading state while the comparison is pending', () => {
    renderChart(null);
    expect(screen.getByRole('status')).toHaveTextContent(/loading/i);
  });

  it('shows an error state when the request fails', async () => {
    mockedGet.mockRejectedValue(new Error('boom'));
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <SessionComparisonChart />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not load session comparison/i,
    );
  });

  it('carries an equity-only session flat across a weekend alongside a crypto session', async () => {
    // Equity-only session: Thu + Fri, no weekend snapshots. Crypto session: also
    // has Sat + Sun. The equity line must extend flat over the weekend (at its
    // Friday value) instead of ending on Friday.
    renderChart([
      series('eq', 'Equity', 100000, [
        ['2026-01-08', 100000],
        ['2026-01-09', 101000],
      ]),
      series('cr', 'Crypto', 100000, [
        ['2026-01-08', 100000],
        ['2026-01-09', 100500],
        ['2026-01-10', 100800],
        ['2026-01-11', 101200],
      ]),
    ]);

    await screen.findByRole('img', { name: /return percent/i });
    // Switch to Value $ so the plotted data is the raw carried-forward value.
    fireEvent.click(screen.getByRole('button', { name: 'Value $' }));

    const el = screen.getByRole('img', { name: /portfolio value/i });
    const option = JSON.parse(el.getAttribute('data-option') ?? '{}');
    const plotted = option.series as Array<{
      id: string;
      data: [number, number][];
    }>;
    const equity = plotted.find((s) => s.id === 'eq');
    expect(equity?.data).toEqual([
      [Date.parse('2026-01-08'), 100000],
      [Date.parse('2026-01-09'), 101000],
      [Date.parse('2026-01-10'), 101000], // Saturday carried from Friday
      [Date.parse('2026-01-11'), 101000], // Sunday carried from Friday
    ]);
  });
});
