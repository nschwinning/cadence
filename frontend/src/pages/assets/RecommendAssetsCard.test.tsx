import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { RecommendAssetsCard } from './RecommendAssetsCard';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('RecommendAssetsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers only stock and crypto as category choices', () => {
    renderWithClient(<RecommendAssetsCard />);

    const chips = screen.getAllByRole('checkbox');
    const labels = chips.map((chip) => chip.textContent?.trim());

    expect(labels).toEqual(['Stock', 'Crypto']);
    expect(labels).not.toContain('ETF');
    expect(labels).not.toContain('Fund');
    expect(labels).not.toContain('Other');
  });
});
