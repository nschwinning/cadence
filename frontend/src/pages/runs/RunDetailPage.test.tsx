import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import { RunDetailPage } from './RunDetailPage';
import { apiClient } from '../../api/client';
import type { AIPortfolioRunDetail } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

const detail: AIPortfolioRunDetail = {
  event: {
    id: 'evt-1',
    session_id: 's1',
    portfolio_id: 'p1',
    event_type: 'rebalance',
    status: 'succeeded',
    request_payload: null,
    result_payload: {
      evaluation_summary: 'Rotated toward higher-conviction names.',
      portfolio_health: 'Healthy and well diversified.',
      target_allocations: [
        {
          ticker: 'AAPL',
          company_name: 'Apple Inc.',
          allocation_pct: 0.6,
          investment_thesis: 'Durable franchise.',
          confidence: 0.9,
        },
      ],
    },
    actions_taken: [
      {
        ticker: 'AAPL',
        side: 'buy',
        shares: 10,
        price: 190,
        executed: true,
        reason: 'Bought 10 units',
      },
      {
        ticker: 'NVDA',
        side: 'long',
        shares: 0,
        price: 950,
        executed: false,
        reason: 'Allocation $500 too small for price $950.00',
      },
    ],
    research: [
      { query: 'apple earnings 2026', results: { organic_results: [] }, error: null },
    ],
    error: null,
    duration_ms: 1200,
    created_at: '2026-09-14T00:00:00Z',
    updated_at: '2026-09-14T00:00:00Z',
  },
  trades: [
    {
      id: 'trade-1',
      session_id: 's1',
      ai_portfolio_event_id: 'evt-1',
      ticker: 'AAPL',
      side: 'buy',
      quantity: 10,
      price: 190,
      notional: 1900,
      signal_type: 'entry',
      executed_at: '2026-09-14T09:30:00Z',
      order_id: 'ord-1',
      order_status: 'filled',
      filled_price: 190,
      filled_at: '2026-09-14T09:30:01Z',
    },
  ],
  closed_positions: [
    {
      id: 'pos-1',
      session_id: 's1',
      ai_portfolio_event_id: 'evt-1',
      ticker: 'TSLA',
      quantity: 5,
      entry_price: 200,
      exit_price: 220,
      entry_date: '2026-09-01T00:00:00Z',
      exit_date: '2026-09-14T00:00:00Z',
      realized_pnl: 100,
      return_pct: 0.1,
      holding_days: 13,
    },
  ],
  rebalance_prompt_version: 3,
};

function renderPage(ui: ReactNode, path = '/runs/evt-1') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/runs/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('RunDetailPage', () => {
  it('renders the run reasoning, research, trades, and closed positions', async () => {
    mockedGet.mockResolvedValue({ data: detail });

    renderPage(<RunDetailPage />);

    // Reasoning (rebalance shape).
    expect(
      await screen.findByText('Rotated toward higher-conviction names.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Healthy and well diversified.')).toBeInTheDocument();
    expect(screen.getByText('Durable franchise.')).toBeInTheDocument();

    // Research transcript.
    expect(screen.getByText('apple earnings 2026')).toBeInTheDocument();

    // Opening trade (AAPL also appears in the allocations table) + closed position.
    expect(screen.getAllByRole('link', { name: 'AAPL' }).length).toBeGreaterThan(
      0,
    );
    expect(screen.getByRole('link', { name: 'TSLA' })).toBeInTheDocument();
    // Section headings present.
    expect(screen.getByText('Opening trades')).toBeInTheDocument();
    expect(screen.getByText('Closed positions')).toBeInTheDocument();

    // Skipped orders surface the non-executed ticker and its reason.
    expect(screen.getByText('Skipped / not executed')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'NVDA' })).toBeInTheDocument();
    expect(
      screen.getByText('Allocation $500 too small for price $950.00'),
    ).toBeInTheDocument();

    // The frozen rebalance-prompt version used for this run.
    expect(screen.getByText('Prompt version')).toBeInTheDocument();
    expect(screen.getByText('v3')).toBeInTheDocument();
  });

  it('surfaces an error when the run cannot be loaded', async () => {
    mockedGet.mockRejectedValue(new Error('not found'));

    renderPage(<RunDetailPage />);

    expect(await screen.findByText('Could not load run')).toBeInTheDocument();
  });
});
