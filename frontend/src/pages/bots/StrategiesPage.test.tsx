import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { StrategiesPage } from './StrategiesPage';
import { apiClient } from '../../api/client';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const CATALOG = [
  {
    key: 'ma_crossover',
    display_name: 'MA Crossover',
    explanation:
      'Buys when the fast SMA crosses above the slow SMA. More detail follows here.',
    required_history: 51,
    params_schema: {},
  },
];

function renderPage(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('StrategiesPage (index)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists catalog strategies, links each to its detail page, and documents capital & risk once', async () => {
    mockedGet.mockResolvedValue({ data: CATALOG });

    renderPage(<StrategiesPage />);

    const link = await screen.findByRole('link', { name: /MA Crossover/i });
    expect(link).toHaveAttribute('href', '/bots/strategies/ma_crossover');
    // Blurb = first sentence of the explanation.
    expect(
      screen.getByText('Buys when the fast SMA crosses above the slow SMA.'),
    ).toBeInTheDocument();
    // Shared capital & risk docs render once on the index.
    expect(screen.getByText('Shared budget ceiling')).toBeInTheDocument();
    expect(screen.getByText('ATR position sizing')).toBeInTheDocument();
    expect(screen.getAllByText('Per-name cap')).toHaveLength(1);
  });

  it('shows a loading state while the catalog is pending', () => {
    mockedGet.mockReturnValue(new Promise(() => {}));

    renderPage(<StrategiesPage />);

    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error state when the catalog fails to load', async () => {
    mockedGet.mockRejectedValue(new Error('boom'));

    renderPage(<StrategiesPage />);

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});
