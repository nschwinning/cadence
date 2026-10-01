import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RecentActivityFeed } from './RecentActivityFeed';
import { makeOverview } from './fixtures';

describe('RecentActivityFeed', () => {
  it('renders entries with status, label and a run link', () => {
    const entries = makeOverview().recent_activity;
    render(
      <MemoryRouter>
        <RecentActivityFeed entries={entries} />
      </MemoryRouter>,
    );
    expect(screen.getByText('Portfolio A')).toBeInTheDocument();
    expect(screen.getByText('rebalance')).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', '/runs/run-1');
  });

  it('shows an empty state with no activity', () => {
    render(
      <MemoryRouter>
        <RecentActivityFeed entries={[]} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/No activity in this range/)).toBeInTheDocument();
  });
});
