import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { UniverseSection } from './UniverseSection';
import { makeOverview } from './fixtures';

describe('UniverseSection', () => {
  it('renders the balance summary and best/worst performers', () => {
    const o = makeOverview();
    render(
      <MemoryRouter>
        <UniverseSection
          balance={o.universe_balance}
          performers={o.universe_performers}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText('Eligible assets')).toBeInTheDocument();
    expect(screen.getByText('90')).toBeInTheDocument();
    expect(screen.getByText('Sectors covered')).toBeInTheDocument();

    expect(screen.getByText('Top performers')).toBeInTheDocument();
    expect(screen.getByText('Worst performers')).toBeInTheDocument();
    // TECH is best, FIN is worst — each ticker appears once.
    expect(screen.getByText('TECH')).toBeInTheDocument();
    expect(screen.getByText('FIN')).toBeInTheDocument();
  });

  it('shows a per-list empty state when there are no performers', () => {
    const o = makeOverview({
      universe_performers: { best: [], worst: [] },
    });
    render(
      <MemoryRouter>
        <UniverseSection
          balance={o.universe_balance}
          performers={o.universe_performers}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getAllByText(/No price history in this range yet/),
    ).toHaveLength(2);
  });
});
