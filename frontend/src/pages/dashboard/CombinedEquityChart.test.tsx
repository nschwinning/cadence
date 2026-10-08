import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CombinedEquityChart } from './CombinedEquityChart';
import { makeSession } from './fixtures';

const sessions = [
  makeSession({ id: 'a', label: 'Alpha' }),
  makeSession({ id: 'b', label: 'Beta' }),
];

// jsdom has no layout; stub the hover wrapper box to a known 800px width so a
// pointer clientX maps deterministically to a point on the time axis.
function stubWrapper(svg: Element) {
  const wrapper = svg.parentElement as HTMLElement;
  wrapper.getBoundingClientRect = () =>
    ({
      width: 800,
      height: 160,
      left: 0,
      top: 0,
      right: 800,
      bottom: 160,
      x: 0,
      y: 0,
      toJSON: () => {},
    }) as DOMRect;
  return wrapper;
}

describe('CombinedEquityChart', () => {
  it('draws the summed line when sessions are selected', () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a', 'b'])}
        onToggle={() => {}}
      />,
    );
    expect(screen.getByTestId('equity-line')).toBeInTheDocument();
    expect(screen.queryByTestId('equity-empty')).not.toBeInTheDocument();
  });

  it('shows the empty state when nothing is selected', () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set()}
        onToggle={() => {}}
      />,
    );
    expect(screen.getByTestId('equity-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('equity-line')).not.toBeInTheDocument();
  });

  it('shows a hover tooltip with the summed value and date at the nearest point', () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a', 'b'])}
        onToggle={() => {}}
      />,
    );
    const svg = screen.getByRole('img', { name: /combined portfolio value/i });
    const wrapper = stubWrapper(svg);
    // Far right maps to the latest date; both sessions sum to 22,000 there.
    fireEvent.pointerMove(wrapper, { clientX: 800 });

    const tooltip = screen.getByTestId('chart-tooltip');
    expect(within(tooltip).getByText('Combined value')).toBeInTheDocument();
    expect(within(tooltip).getByText('$22,000.00')).toBeInTheDocument();
    expect(within(tooltip).getByText('Jun 15, 2026')).toBeInTheDocument();
  });

  it('dismisses the hover tooltip when the pointer leaves the plot', () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a', 'b'])}
        onToggle={() => {}}
      />,
    );
    const svg = screen.getByRole('img', { name: /combined portfolio value/i });
    const wrapper = stubWrapper(svg);
    fireEvent.pointerMove(wrapper, { clientX: 800 });
    expect(screen.getByTestId('chart-tooltip')).toBeInTheDocument();

    fireEvent.pointerLeave(wrapper);
    expect(screen.queryByTestId('chart-tooltip')).not.toBeInTheDocument();
  });

  it('does not show a hover tooltip in the empty state', () => {
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set()}
        onToggle={() => {}}
      />,
    );
    expect(screen.getByTestId('equity-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('chart-tooltip')).not.toBeInTheDocument();
  });

  it('toggles a session via its legend checkbox', async () => {
    const onToggle = vi.fn();
    render(
      <CombinedEquityChart
        sessions={sessions}
        selectedIds={new Set(['a', 'b'])}
        onToggle={onToggle}
      />,
    );
    await userEvent.click(screen.getByRole('checkbox', { name: /Beta/ }));
    expect(onToggle).toHaveBeenCalledWith('b');
  });
});
