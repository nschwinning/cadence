import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { PortfolioLeaderboard } from './PortfolioLeaderboard';
import { makeSession } from './fixtures';

function renderWithRouter(ui: ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe('PortfolioLeaderboard', () => {
  const low = makeSession({
    id: 'low',
    label: 'Laggard',
    current_value: 10500,
    pnl: 500,
  }); // +5%
  const high = makeSession({
    id: 'high',
    label: 'Leader',
    current_value: 12000,
    pnl: 2000,
  }); // +20%

  it('sorts by range return descending', () => {
    renderWithRouter(<PortfolioLeaderboard sessions={[low, high]} />);
    const links = screen.getAllByRole('link');
    expect(links[0]).toHaveTextContent('Leader');
    expect(links[1]).toHaveTextContent('Laggard');
  });

  it('links each row to its session detail page', () => {
    renderWithRouter(<PortfolioLeaderboard sessions={[high]} />);
    expect(screen.getByRole('link', { name: 'Leader' })).toHaveAttribute(
      'href',
      '/paper-trading/high',
    );
  });

  it('drops a deselected portfolio (fewer rows)', () => {
    const { rerender } = renderWithRouter(
      <PortfolioLeaderboard sessions={[low, high]} />,
    );
    expect(screen.getAllByRole('link')).toHaveLength(2);

    rerender(
      <MemoryRouter>
        <PortfolioLeaderboard sessions={[high]} />
      </MemoryRouter>,
    );
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveTextContent('Leader');
  });

  it('shows an empty message when nothing is selected', () => {
    renderWithRouter(<PortfolioLeaderboard sessions={[]} />);
    expect(screen.getByText(/No portfolios selected/)).toBeInTheDocument();
  });

  it('renders the return for a row', () => {
    renderWithRouter(<PortfolioLeaderboard sessions={[high]} />);
    const row = screen.getByRole('link', { name: 'Leader' }).closest('tr');
    expect(within(row as HTMLElement).getByText('20.00%')).toBeInTheDocument();
  });
});
