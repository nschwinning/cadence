import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PerformanceTiles, ValueTiles } from './HeroTiles';
import { makeSession } from './fixtures';

describe('ValueTiles (point-in-time value band)', () => {
  it('renders the four live figures with the correct values and sign colours', () => {
    const sessions = [
      makeSession({
        id: 'a',
        current_value: 12000,
        contributions: [{ effective_date: '2026-06-01', amount: 10000 }],
        benchmark_value: 11000,
      }),
    ];
    render(<ValueTiles sessions={sessions} />);

    // All four labels are present.
    expect(screen.getByText('Total value')).toBeInTheDocument();
    expect(screen.getByText('Total return')).toBeInTheDocument();
    expect(screen.getByText('Lifetime P&L')).toBeInTheDocument();
    expect(screen.getByText('Return vs benchmark')).toBeInTheDocument();

    // Total value = 12000; lifetime P&L = 12000 − 10000 = 2000 (gain → emerald).
    expect(screen.getByText('$12,000.00')).toBeInTheDocument();
    expect(screen.getByText('$2,000.00')).toHaveClass('text-emerald-700');
    // Total return = 2000/10000 = 20.00% (gain → emerald).
    expect(screen.getByText('20.00%')).toHaveClass('text-emerald-700');
    // Benchmark return = (11000−10000)/10000 = 10%; excess = 20% − 10% = 10.00%.
    expect(screen.getByText('10.00%')).toHaveClass('text-emerald-700');
  });

  it('colours a negative lifetime P&L and excess as a loss', () => {
    const sessions = [
      makeSession({
        id: 'a',
        current_value: 9000,
        contributions: [{ effective_date: '2026-06-01', amount: 10000 }],
        benchmark_value: 10500, // benchmark up 5%, portfolio down 10% → excess −15%
      }),
    ];
    render(<ValueTiles sessions={sessions} />);
    expect(screen.getByText('-$1,000.00')).toHaveClass('text-red-700');
    expect(screen.getByText('-15.00%')).toHaveClass('text-red-700');
  });

  it('shows "Not yet available" when a selected session has no benchmark value', () => {
    const sessions = [
      makeSession({ id: 'a', benchmark_value: 11000 }),
      makeSession({ id: 'b', benchmark_value: null }),
    ];
    render(<ValueTiles sessions={sessions} />);
    expect(screen.getByText('Not yet available')).toBeInTheDocument();
  });

  it('shows an em dash for total return when there is no contributed basis', () => {
    const sessions = [
      makeSession({ id: 'a', current_value: 5000, contributions: [] }),
    ];
    render(<ValueTiles sessions={sessions} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('re-aggregates the four figures when the selection changes, without a refetch', () => {
    const a = makeSession({
      id: 'a',
      current_value: 12000,
      contributions: [{ effective_date: '2026-06-01', amount: 10000 }],
      benchmark_value: 11000,
    });
    const b = makeSession({
      id: 'b',
      current_value: 24000,
      contributions: [{ effective_date: '2026-06-01', amount: 20000 }],
      benchmark_value: 22000,
    });
    const { rerender } = render(<ValueTiles sessions={[a, b]} />);
    // Σ value 36000; contributed 30000; lifetime P&L 6000; return 20%.
    expect(screen.getByText('$36,000.00')).toBeInTheDocument();
    expect(screen.getByText('$6,000.00')).toBeInTheDocument();

    // Deselecting b recomputes purely from props (no new data fetched).
    rerender(<ValueTiles sessions={[a]} />);
    expect(screen.getByText('$12,000.00')).toBeInTheDocument();
    expect(screen.getByText('$2,000.00')).toBeInTheDocument();
  });
});

describe('PerformanceTiles (range-scoped performance band)', () => {
  it('reflects the range realised/unrealised/return/fees aggregate', () => {
    const sessions = [
      makeSession({
        id: 'a',
        pnl: 1000,
        realised_pnl: 600,
        unrealised_pnl: 400,
        fees: 2,
      }),
      makeSession({
        id: 'b',
        current_value: 20000,
        pnl: 0,
        realised_pnl: -100,
        unrealised_pnl: 100,
        fees: 3,
      }),
    ];
    render(<PerformanceTiles sessions={sessions} range="1M" />);

    expect(screen.getByText('Realised P&L')).toBeInTheDocument();
    expect(screen.getByText('Unrealised P&L')).toBeInTheDocument();
    // realised Σ = 600 - 100 = 500; unrealised Σ = 400 + 100 = 500
    expect(screen.getAllByText('$500.00')).toHaveLength(2);
    expect(screen.getByText('$5.00')).toBeInTheDocument(); // fees
  });

  it('is zeroed when nothing is selected', () => {
    render(<PerformanceTiles sessions={[]} range="1M" />);
    // realised, unrealised and fees all read $0.00
    expect(screen.getAllByText('$0.00').length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText('0.00%')).toBeInTheDocument();
  });
});
