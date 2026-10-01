import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RangeSelector } from './RangeSelector';

describe('RangeSelector', () => {
  it('marks the active range and calls onChange when another is picked', async () => {
    const onChange = vi.fn();
    render(<RangeSelector value="1M" onChange={onChange} />);

    expect(screen.getByRole('button', { name: '1M' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'YTD' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );

    await userEvent.click(screen.getByRole('button', { name: 'YTD' }));
    expect(onChange).toHaveBeenCalledWith('YTD');
  });

  it('renders all six ranges', () => {
    render(<RangeSelector value="1D" onChange={() => {}} />);
    for (const r of ['1D', '1W', '1M', 'YTD', '1Y', 'Max']) {
      expect(screen.getByRole('button', { name: r })).toBeInTheDocument();
    }
  });
});
