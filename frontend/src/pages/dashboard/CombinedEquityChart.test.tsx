import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CombinedEquityChart } from './CombinedEquityChart';
import { makeSession } from './fixtures';

const sessions = [
  makeSession({ id: 'a', label: 'Alpha' }),
  makeSession({ id: 'b', label: 'Beta' }),
];

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
