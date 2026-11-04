import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FreshnessBadge } from './PaperTradingSessionPage';

describe('FreshnessBadge', () => {
  it('renders the live kind', () => {
    render(<FreshnessBadge kind="live" />);
    expect(screen.getByTestId('freshness-live')).toHaveTextContent(/live/i);
  });

  it('renders the end-of-day kind', () => {
    render(<FreshnessBadge kind="eod" />);
    expect(screen.getByTestId('freshness-eod')).toHaveTextContent(/end of day/i);
  });

  it('renders the intraday kind', () => {
    render(<FreshnessBadge kind="intraday" />);
    const badge = screen.getByTestId('freshness-intraday');
    expect(badge).toHaveTextContent(/intraday/i);
    // Neutral styling, not the green "live" treatment.
    expect(badge.className).toContain('bg-slate-100');
  });
});
