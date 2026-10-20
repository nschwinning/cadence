import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import App from './App';

function renderApp(initialEntry = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
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

  it('redirects the legacy /paper-trading route to the unified Portfolios list', async () => {
    renderApp('/paper-trading');

    // The unified Portfolios list renders its heading regardless of query state.
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Portfolios' }),
    ).toBeInTheDocument();
  });

  it('redirects a legacy /paper-trading/:id deep link to /portfolios/:id', async () => {
    renderApp('/paper-trading/s1');

    // The unified session detail page renders its back link to Portfolios.
    expect(
      await screen.findByRole('link', { name: /back to portfolios/i }),
    ).toBeInTheDocument();
  });
});
