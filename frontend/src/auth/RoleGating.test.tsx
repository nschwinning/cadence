import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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
});
