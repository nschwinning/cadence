import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BreakdownTile } from './BreakdownTile';

const cap = (k: string) => k.charAt(0).toUpperCase() + k.slice(1);

describe('BreakdownTile donut', () => {
  it('draws a slice per entry with the total in the center', () => {
    const { container } = render(
      <BreakdownTile
        title="By category"
        entries={[
          { key: 'stock', count: 60 },
          { key: 'etf', count: 20 },
        ]}
        formatKey={cap}
      />,
    );

    // One track circle + one slice circle per entry.
    expect(container.querySelectorAll('circle')).toHaveLength(3);

    // Center shows the total count by default.
    expect(screen.getByText('80')).toBeInTheDocument();
    expect(screen.getByText('total')).toBeInTheDocument();
  });

  it('exposes each slice label, exact count, and percentage via aria-label', () => {
    render(
      <BreakdownTile
        title="By category"
        entries={[
          { key: 'stock', count: 60 },
          { key: 'etf', count: 20 },
        ]}
        formatKey={cap}
      />,
    );
    expect(
      screen.getByRole('button', { name: 'Stock: 60 (75.0%)' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Etf: 20 (25.0%)' }),
    ).toBeInTheDocument();
  });

  it('renders no persistent legend — slice identity is hover/focus only', () => {
    render(
      <BreakdownTile
        title="By category"
        entries={[
          { key: 'stock', count: 60 },
          { key: 'etf', count: 20 },
        ]}
        formatKey={cap}
      />,
    );

    // There is exactly one interactive element per entry (the slice), not a
    // slice plus a legend row.
    expect(screen.getAllByRole('button')).toHaveLength(2);

    // No label/percentage text is shown until a slice is hovered/focused.
    expect(screen.queryByText('Stock')).not.toBeInTheDocument();
    expect(screen.queryByText('75.0%')).not.toBeInTheDocument();
  });

  it('reveals the hovered entry detail in the center in place of the total', () => {
    render(
      <BreakdownTile
        title="By category"
        entries={[
          { key: 'stock', count: 60 },
          { key: 'etf', count: 20 },
        ]}
        formatKey={cap}
      />,
    );

    // Before hover: the center shows the total.
    expect(screen.getByText('total')).toBeInTheDocument();
    expect(screen.queryByText('Stock')).not.toBeInTheDocument();

    fireEvent.mouseEnter(
      screen.getByRole('button', { name: 'Stock: 60 (75.0%)' }),
    );

    // After hover: the center switches to the active slice's label/count/percentage.
    expect(screen.queryByText('total')).not.toBeInTheDocument();
    expect(screen.getByText('Stock')).toBeInTheDocument();
    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.getByText('75.0%')).toBeInTheDocument();
  });

  it('renders the empty state and no chart when there are no entries', () => {
    const { container } = render(<BreakdownTile title="By sector" entries={[]} />);

    expect(screen.getByText('No data yet')).toBeInTheDocument();
    expect(container.querySelectorAll('circle')).toHaveLength(0);
  });

  it('treats a zero total as empty rather than dividing by zero', () => {
    const { container } = render(
      <BreakdownTile title="By sector" entries={[{ key: 'x', count: 0 }]} />,
    );
    expect(screen.getByText('No data yet')).toBeInTheDocument();
    expect(container.querySelectorAll('circle')).toHaveLength(0);
  });
});
