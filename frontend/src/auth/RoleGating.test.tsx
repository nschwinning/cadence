import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { Role } from './roles';

// The signed-in user's roles, switched per test.
let currentRoles = new Set<Role>(['viewer', 'trader', 'admin']);
vi.mock('./useRoles', () => ({
  useRoles: () => currentRoles,
  useHasRole: (role: Role) => currentRoles.has(role),
}));
vi.mock('../api/client', () => ({
  apiClient: {
    get: vi.fn((url: string) =>
      Promise.resolve({ data: url.endsWith('/bots/strategies') ? [] : { items: [], total: 0 } }),
    ),
  },
}));

const { Sidebar } = await import('../components/layout/Sidebar');
const { BotsPage } = await import('../pages/bots/BotsPage');
const { WatchlistPage } = await import('../pages/watchlist/WatchlistPage');
const { apiClient } = await import('../api/client');

function renderWithProviders(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('role-aware interface', () => {
  beforeEach(() => {
    currentRoles = new Set<Role>(['viewer', 'trader', 'admin']);
  });

  it('shows the Admin entry to admins only', () => {
    renderWithProviders(<Sidebar isOpen={false} onClose={() => {}} />);
    expect(screen.getByRole('link', { name: /admin/i })).toBeInTheDocument();
  });

  it('hides the Admin entry from traders', () => {
    currentRoles = new Set<Role>(['viewer', 'trader']);
    renderWithProviders(<Sidebar isOpen={false} onClose={() => {}} />);
    expect(screen.queryByRole('link', { name: /admin/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /bots/i })).toBeInTheDocument();
  });

  it('offers no build-a-bot control to viewers', () => {
    currentRoles = new Set<Role>(['viewer']);
    renderWithProviders(<BotsPage />);
    expect(screen.queryByRole('button', { name: 'Build a bot' })).not.toBeInTheDocument();
  });

  it('offers build-a-bot to traders', () => {
    currentRoles = new Set<Role>(['viewer', 'trader']);
    renderWithProviders(<BotsPage />);
    expect(screen.getByRole('button', { name: 'Build a bot' })).toBeInTheDocument();
  });

  it('shows the All users toggle to admins and requests every user\'s bots', async () => {
    renderWithProviders(<BotsPage />);
    const toggle = screen.getByRole('checkbox', { name: 'All users' });

    fireEvent.click(toggle);

    await waitFor(() =>
      expect(vi.mocked(apiClient.get)).toHaveBeenCalledWith(
        '/api/v1/bots/sessions',
        expect.objectContaining({ params: expect.objectContaining({ scope: 'all' }) }),
      ),
    );
  });

  it('hides the All users toggle from traders', () => {
    currentRoles = new Set<Role>(['viewer', 'trader']);
    renderWithProviders(<BotsPage />);
    expect(screen.queryByRole('checkbox', { name: 'All users' })).not.toBeInTheDocument();
  });

  it('offers watchlist discovery to admins only', () => {
    renderWithProviders(<WatchlistPage />);
    expect(screen.getByRole('button', { name: 'Discover' })).toBeInTheDocument();
  });

  it('hides watchlist discovery from traders', () => {
    currentRoles = new Set<Role>(['viewer', 'trader']);
    renderWithProviders(<WatchlistPage />);
    expect(screen.queryByRole('button', { name: 'Discover' })).not.toBeInTheDocument();
  });
});
