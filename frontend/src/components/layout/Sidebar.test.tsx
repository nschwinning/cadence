import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from './Sidebar';

function renderSidebar() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Sidebar isOpen={false} onClose={() => {}} />
    </MemoryRouter>,
  );
}

describe('Sidebar', () => {
  it('renders the Technical Indicators nav entry linking to its route', () => {
    renderSidebar();

    const link = screen.getByRole('link', { name: /technical indicators/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/technical-indicators');
  });

  it('renders the System nav entry linking to its route', () => {
    renderSidebar();

    const link = screen.getByRole('link', { name: /^system$/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/system');
  });
});
