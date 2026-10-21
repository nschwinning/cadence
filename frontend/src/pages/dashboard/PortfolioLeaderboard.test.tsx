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
    renderWithRouter(<PortfolioLeaderboard sessions={[low, high]} range="1M" />);
    const links = screen.getAllByRole('link');
    expect(links[0]).toHaveTextContent('Leader');
    expect(links[1]).toHaveTextContent('Laggard');
  });

  it('links each row to its session detail page', () => {
    renderWithRouter(<PortfolioLeaderboard sessions={[high]} range="1M" />);
    expect(screen.getByRole('link', { name: 'Leader' })).toHaveAttribute(
      'href',
      '/paper-trading/high',
    );
  });

  it('drops a deselected portfolio (fewer rows)', () => {
    const { rerender } = renderWithRouter(
      <PortfolioLeaderboard sessions={[low, high]} range="1M" />,
    );
    expect(screen.getAllByRole('link')).toHaveLength(2);

    rerender(
      <MemoryRouter>
        <PortfolioLeaderboard sessions={[high]} range="1M" />
      </MemoryRouter>,
    );
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveTextContent('Leader');
  });

  it('shows an empty message when nothing is selected', () => {
    renderWithRouter(<PortfolioLeaderboard sessions={[]} range="1M" />);
    expect(screen.getByText(/No portfolios selected/)).toBeInTheDocument();
  });

  it('renders the return for a row', () => {
    renderWithRouter(<PortfolioLeaderboard sessions={[high]} range="1M" />);
    const row = screen.getByRole('link', { name: 'Leader' }).closest('tr');
    expect(within(row as HTMLElement).getByText('20.00%')).toBeInTheDocument();
  });

  it('renders range realised/unrealised cells per row', () => {
    const s = makeSession({
      id: 'x',
      label: 'Triple',
      current_value: 12000,
      pnl: 2000,
      realised_pnl: 1500,
      unrealised_pnl: 500,
    });
    renderWithRouter(<PortfolioLeaderboard sessions={[s]} range="1M" />);
    const row = screen.getByRole('link', { name: 'Triple' }).closest('tr');
    expect(
      within(row as HTMLElement).getByText('$1,500.00'),
    ).toBeInTheDocument(); // realised
    expect(within(row as HTMLElement).getByText('$500.00')).toBeInTheDocument(); // unrealised
  });

  it('groups the range columns under a spanning sub-header tracking the range', () => {
    const { rerender } = renderWithRouter(
      <PortfolioLeaderboard sessions={[high]} range="1M" />,
    );
    expect(screen.getByText('Over the past month')).toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <PortfolioLeaderboard sessions={[high]} range="YTD" />
      </MemoryRouter>,
    );
    expect(screen.getByText('Over year to date')).toBeInTheDocument();
  });
});
