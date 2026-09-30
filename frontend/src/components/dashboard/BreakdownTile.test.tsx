import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { BreakdownTile } from './BreakdownTile';

const cap = (k: string) => k.charAt(0).toUpperCase() + k.slice(1);

describe('BreakdownTile donut', () => {
  it('draws a slice per entry with the total in the center and a labelled legend', () => {
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

    // Center shows the total count.
    expect(screen.getByText('80')).toBeInTheDocument();
    expect(screen.getByText('total')).toBeInTheDocument();

    // Legend lists each humanized label with its exact count and percentage.
    expect(screen.getByText('Stock')).toBeInTheDocument();
    expect(screen.getByText('Etf')).toBeInTheDocument();
    expect(screen.getByText('75.0%')).toBeInTheDocument(); // 60 / 80
    expect(screen.getByText('25.0%')).toBeInTheDocument(); // 20 / 80
  });

  it('each slice and legend row exposes label, exact count, and percentage via aria-label', () => {
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
    // Both the slice and the legend row carry the same accessible detail.
    expect(
      screen.getAllByRole('button', { name: 'Stock: 60 (75.0%)' }).length,
    ).toBeGreaterThanOrEqual(2);
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
    expect(screen.getAllByText('Stock')).toHaveLength(1); // legend only

    fireEvent.mouseEnter(
      screen.getAllByRole('button', { name: 'Stock: 60 (75.0%)' })[0],
    );

    // After hover: the center switches to the active slice's detail.
    expect(screen.queryByText('total')).not.toBeInTheDocument();
    expect(screen.getAllByText('Stock')).toHaveLength(2); // legend + center
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

  it('scopes counts so the legend shows the exact value', () => {
    render(
      <BreakdownTile
        title="By sector"
        entries={[{ key: 'technology', count: 40 }]}
        formatKey={cap}
      />,
    );
    // Both the SVG slice and the legend row expose the same aria-label; the
    // legend row is the real <button> element that also renders the count/pct text.
    const legend = screen
      .getAllByRole('button', { name: 'Technology: 40 (100.0%)' })
      .find((el) => el.tagName === 'BUTTON');
    expect(legend).toBeDefined();
    expect(within(legend!).getByText('40')).toBeInTheDocument();
    expect(within(legend!).getByText('100.0%')).toBeInTheDocument();
  });
});
