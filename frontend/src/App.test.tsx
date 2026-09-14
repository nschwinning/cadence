import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import App from './App';

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('App shell', () => {
  it('renders the branded shell around the Dashboard placeholder', () => {
    renderApp();

    // Brand name appears in the header and the Dashboard heading.
    expect(screen.getAllByText('Cadence').length).toBeGreaterThan(0);

    // Side menu: the single Dashboard destination link.
    expect(
      screen.getByRole('link', { name: /dashboard/i }),
    ).toBeInTheDocument();
  });
});
