import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HeroTiles } from './HeroTiles';
import { makeSession } from './fixtures';

describe('HeroTiles', () => {
  it('reflects the aggregate of the given (selected) sessions', () => {
    const sessions = [
      makeSession({ id: 'a', current_value: 11000, pnl: 1000, fees: 2 }),
      makeSession({ id: 'b', current_value: 20000, pnl: 0, fees: 3 }),
    ];
    render(<HeroTiles sessions={sessions} range="1M" />);

    expect(screen.getByText('Total value')).toBeInTheDocument();
    expect(screen.getByText('$31,000.00')).toBeInTheDocument();
    // money-weighted return = 1000 / 30000 = 3.33%
    expect(screen.getByText('3.33%')).toBeInTheDocument();
    expect(screen.getByText('$5.00')).toBeInTheDocument(); // fees
  });

  it('recomputes when the selection changes (fewer sessions)', () => {
    const { rerender } = render(
      <HeroTiles
        sessions={[makeSession({ id: 'a', current_value: 11000, pnl: 1000 })]}
        range="1M"
      />,
    );
    expect(screen.getByText('$11,000.00')).toBeInTheDocument();

    rerender(<HeroTiles sessions={[]} range="1M" />);
    // total value, P&L and fees all read $0.00 with nothing selected
    expect(screen.getAllByText('$0.00').length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText('0.00%')).toBeInTheDocument();
  });
});
