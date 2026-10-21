import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PerformanceTiles, ValueTiles } from './HeroTiles';
import { makeSession } from './fixtures';

describe('ValueTiles (point-in-time value band)', () => {
  it('sums the current value of the given (selected) sessions', () => {
    const sessions = [
      makeSession({ id: 'a', current_value: 11000 }),
      makeSession({ id: 'b', current_value: 20000 }),
    ];
    render(<ValueTiles sessions={sessions} />);
    expect(screen.getByText('Total value')).toBeInTheDocument();
    expect(screen.getByText('$31,000.00')).toBeInTheDocument();
  });

  it('recomputes when the selection changes (fewer sessions)', () => {
    const { rerender } = render(
      <ValueTiles sessions={[makeSession({ id: 'a', current_value: 11000 })]} />,
    );
    expect(screen.getByText('$11,000.00')).toBeInTheDocument();

    rerender(<ValueTiles sessions={[]} />);
    expect(screen.getByText('$0.00')).toBeInTheDocument();
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
