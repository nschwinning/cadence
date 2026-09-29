import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { SessionComparisonChart } from './SessionComparisonChart';
import { apiClient } from '../../api/client';
import type { SessionValueComparisonSeries } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

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
  const ui: ReactNode = <SessionComparisonChart />;
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('SessionComparisonChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders one line per plottable session with a legend', async () => {
    const { container } = renderChart([
      series('a', 'Alpha', 100000, [
        ['2026-01-04', 100000],
        ['2026-01-05', 101000],
      ]),
      series('b', 'Beta', 50000, [
        ['2026-01-04', 50000],
        ['2026-01-05', 52000],
      ]),
    ]);

    await screen.findByRole('img', { name: /return percent/i });
    expect(
      container.querySelectorAll('[data-testid="comparison-line"]'),
    ).toHaveLength(2);
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  it('toggles between the return % and value $ metrics', async () => {
    renderChart([
      series('a', 'Alpha', 100000, [
        ['2026-01-04', 100000],
        ['2026-01-05', 110000],
      ]),
    ]);

    // Default is the return metric: +10% shows in the legend summary.
    await screen.findByRole('img', { name: /return percent/i });
    expect(screen.getByText(/· 10\.00%/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Value $' }));

    // Value metric: the y-axis rescales and the legend shows the dollar value.
    expect(
      screen.getByRole('img', { name: /portfolio value/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/· \$110,000\.00/)).toBeInTheDocument();
  });

  it('labels the axes and switches the y-axis units with the metric', async () => {
    renderChart([
      series('a', 'Alpha', 100000, [
        ['2026-01-04', 100000],
        ['2026-01-06', 110000],
      ]),
    ]);

    await screen.findByRole('img', { name: /return percent/i });
    // Default return view: y-axis top tick is the max return %; x-axis is dated.
    let yLabels = screen.getAllByTestId('chart-y-label');
    expect(yLabels[0]).toHaveTextContent('10.00%');
    const xLabels = screen.getAllByTestId('chart-x-label');
    expect(xLabels.map((el) => el.textContent)).toEqual(['1/4', '1/6']);

    fireEvent.click(screen.getByRole('button', { name: 'Value $' }));

    // Value view: y-axis top tick becomes the max value in USD.
    yLabels = screen.getAllByTestId('chart-y-label');
    expect(yLabels[0]).toHaveTextContent('$110,000.00');
  });

  it('shows no axis labels in the placeholder state', async () => {
    renderChart([series('a', 'Alpha', 100000, [['2026-01-04', 100000]])]);

    await screen.findByTestId('comparison-placeholder');
    expect(screen.queryByTestId('chart-axes')).not.toBeInTheDocument();
    expect(screen.queryAllByTestId('chart-y-label')).toHaveLength(0);
  });

  it('legends but does not plot a session with fewer than two points', async () => {
    const { container } = renderChart([
      series('a', 'Alpha', 100000, [
        ['2026-01-04', 100000],
        ['2026-01-05', 101000],
      ]),
      series('b', 'Beta', 100000, [['2026-01-04', 100000]]),
    ]);

    await screen.findByRole('img', { name: /return percent/i });
    expect(
      container.querySelectorAll('[data-testid="comparison-line"]'),
    ).toHaveLength(1);
    // Beta is still legended, marked as having no chart data.
    expect(screen.getByText('Beta')).toBeInTheDocument();
    expect(screen.getByText(/no chart data/i)).toBeInTheDocument();
  });

  it('shows the placeholder when no session has enough points', async () => {
    const { container } = renderChart([
      series('a', 'Alpha', 100000, [['2026-01-04', 100000]]),
    ]);

    expect(
      await screen.findByTestId('comparison-placeholder'),
    ).toHaveTextContent(/not enough history to compare yet/i);
    expect(
      container.querySelectorAll('[data-testid="comparison-line"]'),
    ).toHaveLength(0);
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
});
