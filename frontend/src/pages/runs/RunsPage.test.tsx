import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { RunsPage } from './RunsPage';
import { apiClient } from '../../api/client';
import type { AIPortfolioEvent } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

function makeRun(overrides: Partial<AIPortfolioEvent> = {}): AIPortfolioEvent {
  return {
    id: 'evt-1',
    session_id: 's1',
    portfolio_id: 'p1',
    event_type: 'rebalance',
    status: 'succeeded',
    request_payload: null,
    result_payload: null,
    actions_taken: [{ ticker: 'AAPL' }],
    research: [{ query: 'q', results: null, error: null }],
    error: null,
    duration_ms: 1200,
    created_at: '2026-09-14T00:00:00Z',
    updated_at: '2026-09-14T00:00:00Z',
    ...overrides,
  };
}

function renderPage(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('RunsPage', () => {
  it('lists AI runs with a link to each run detail', async () => {
    mockedGet.mockResolvedValue({
      data: { items: [makeRun()], total: 1 },
    });

    renderPage(<RunsPage />);

    const link = await screen.findByRole('link', {
      name: new Date('2026-09-14T00:00:00Z').toLocaleString(),
    });
    expect(link).toHaveAttribute('href', '/runs/evt-1');
    expect(screen.getByText('1 total')).toBeInTheDocument();
    // Action + research counts surface in the row.
    const row = link.closest('tr') as HTMLElement;
    expect(within(row).getByText('rebalance')).toBeInTheDocument();
  });

  it('shows an empty state when there are no runs', async () => {
    mockedGet.mockResolvedValue({ data: { items: [], total: 0 } });

    renderPage(<RunsPage />);

    expect(await screen.findByText(/No AI runs yet/)).toBeInTheDocument();
  });

  it('passes the event_type filter when a type is selected', async () => {
    mockedGet.mockResolvedValue({ data: { items: [], total: 0 } });

    renderPage(<RunsPage />);
    await screen.findByText(/No AI runs yet/);

    await userEvent.click(screen.getByRole('button', { name: 'Builds' }));

    // The most recent request carries the build filter.
    const lastCall = mockedGet.mock.calls.at(-1);
    expect(lastCall?.[0]).toBe('/api/v1/ai-portfolio/runs');
    expect(lastCall?.[1]).toMatchObject({
      params: expect.objectContaining({ event_type: 'build' }),
    });
  });
});
