import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from './Sidebar';

function renderSidebar(initialEntry: string | { pathname: string; state: unknown } = '/') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Sidebar isOpen={false} onClose={() => {}} />
    </MemoryRouter>,
  );
}

/** Active nav links carry the emerald highlight class. */
function isHighlighted(link: HTMLElement): boolean {
  return link.className.includes('bg-emerald-500');
}

describe('Sidebar', () => {
  it('renders the Technical Indicators nav entry linking to its route', () => {
    renderSidebar();

    const link = screen.getByRole('link', { name: /technical indicators/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/technical-indicators');
  });

  it('renders the Watchlist nav entry linking to its route', () => {
    renderSidebar();

    const link = screen.getByRole('link', { name: /watchlist/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/watchlist');
  });

  it('renders the System nav entry linking to its route', () => {
    renderSidebar();

    const link = screen.getByRole('link', { name: /^system$/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/system');
  });

  it('renders a single Portfolios nav entry and no Paper Trading entry', () => {
    renderSidebar();

    const portfolios = screen.getAllByRole('link', { name: /portfolios/i });
    expect(portfolios).toHaveLength(1);
    expect(portfolios[0]).toHaveAttribute('href', '/portfolios');
    expect(
      screen.queryByRole('link', { name: /paper trading/i }),
    ).not.toBeInTheDocument();
  });

  it('highlights Watchlist (not Assets) on an asset detail page opened from the watchlist', () => {
    renderSidebar({ pathname: '/assets/AAPL', state: { from: 'watchlist' } });

    expect(isHighlighted(screen.getByRole('link', { name: /watchlist/i }))).toBe(true);
    expect(isHighlighted(screen.getByRole('link', { name: /^assets$/i }))).toBe(false);
  });

  it('highlights Assets (not Watchlist) on an asset detail page reached without watchlist state', () => {
    renderSidebar('/assets/AAPL');

    expect(isHighlighted(screen.getByRole('link', { name: /^assets$/i }))).toBe(true);
    expect(isHighlighted(screen.getByRole('link', { name: /watchlist/i }))).toBe(false);
  });
});
