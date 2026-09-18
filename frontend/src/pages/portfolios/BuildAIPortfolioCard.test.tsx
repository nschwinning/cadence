import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { BuildAIPortfolioCard } from './BuildAIPortfolioCard';
import { apiClient } from '../../api/client';
import { aiPortfolioKeys } from '../../api/aiPortfolio';
import type { AIEventStatus, AIPortfolioEvent } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

function makeEvent(status: AIEventStatus): AIPortfolioEvent {
  return {
    id: 'evt-1',
    session_id: 'sess-1',
    portfolio_id: 'port-1',
    event_type: 'build',
    status,
    request_payload: null,
    result_payload: null,
    actions_taken: null,
    research: null,
    error: null,
    duration_ms: null,
    created_at: '2026-09-14T00:00:00Z',
    updated_at: '2026-09-14T00:00:00Z',
  };
}

const BENCHMARKS = [
  { id: 'SP500', name: 'S&P 500' },
  { id: 'DJIA', name: 'Dow Jones Industrial Average' },
];

/** Route GETs: the benchmark catalog for its endpoint, the build event otherwise. */
function routeGet(status: () => AIEventStatus) {
  return (url: string) => {
    if (url.endsWith('/paper-trading/benchmarks')) {
      return Promise.resolve({ data: BENCHMARKS });
    }
    return Promise.resolve({ data: makeEvent(status()) });
  };
}

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
  return { ...utils, queryClient };
}

describe('BuildAIPortfolioCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not render a candidate-tickers input (the AI uses the whole universe)', () => {
    renderWithClient(<BuildAIPortfolioCard />);

    expect(screen.queryByLabelText('Candidate tickers')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Max positions')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('checkbox', { name: /Allow short positions/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('checkbox', { name: /Allow the AI to add picks/i }),
    ).not.toBeInTheDocument();
  });

  it('starts a build with the default capital, risk profile, asset scope, and rebalancing, and updates to succeeded without manual refresh', async () => {
    let status: AIEventStatus = 'running';
    mockedPost.mockResolvedValue({ data: { event_id: 'evt-1', status: 'queued' } });
    mockedGet.mockImplementation(routeGet(() => status));
    const user = userEvent.setup();

    const { queryClient } = renderWithClient(<BuildAIPortfolioCard />);

    // The capital input defaults to the new $10,000, and asset scope to Both.
    expect(screen.getByLabelText('Capital ($)')).toHaveValue(10000);
    expect(screen.getByLabelText('Asset types')).toHaveValue('both');

    await user.click(screen.getByRole('button', { name: 'Build portfolio' }));

    // Running mode appears from the polled status, no user action needed.
    expect(await screen.findByText('Building portfolio…')).toBeInTheDocument();
    expect(mockedPost).toHaveBeenCalledWith('/api/v1/ai-portfolio/build', {
      allocated_capital: 10000,
      risk_profile: 'balanced',
      asset_types: 'both',
      daily_rebalancing: false,
      benchmark: 'SP500',
    });

    // Backend advances the event to terminal; force the poll's refetch (jsdom
    // does not fire the background interval) — the UI reacts on its own.
    status = 'succeeded';
    await queryClient.refetchQueries({
      queryKey: aiPortfolioKeys.buildStatus('evt-1'),
    });

    expect(await screen.findByText('Build succeeded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Build another' })).toBeInTheDocument();
  });

  it('enrolls in daily rebalancing when the toggle is checked', async () => {
    mockedPost.mockResolvedValue({ data: { event_id: 'evt-1', status: 'queued' } });
    mockedGet.mockImplementation(routeGet(() => 'running'));
    const user = userEvent.setup();

    renderWithClient(<BuildAIPortfolioCard />);

    await user.click(
      screen.getByRole('checkbox', { name: /Enroll in daily rebalancing/i }),
    );
    await user.click(screen.getByRole('button', { name: 'Build portfolio' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/ai-portfolio/build',
      expect.objectContaining({ daily_rebalancing: true }),
    );
  });

  it('sends the selected asset scope with the build request', async () => {
    mockedPost.mockResolvedValue({ data: { event_id: 'evt-1', status: 'queued' } });
    mockedGet.mockImplementation(routeGet(() => 'running'));
    const user = userEvent.setup();

    renderWithClient(<BuildAIPortfolioCard />);

    await user.selectOptions(screen.getByLabelText('Asset types'), 'crypto');
    await user.click(screen.getByRole('button', { name: 'Build portfolio' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/ai-portfolio/build',
      expect.objectContaining({ asset_types: 'crypto' }),
    );
  });

  it('defaults the benchmark to S&P 500 and sends the selected benchmark id', async () => {
    mockedPost.mockResolvedValue({ data: { event_id: 'evt-1', status: 'queued' } });
    mockedGet.mockImplementation(routeGet(() => 'running'));
    const user = userEvent.setup();

    renderWithClient(<BuildAIPortfolioCard />);

    // The benchmark selector defaults to S&P 500 (its SP500 catalog id).
    const select = await screen.findByLabelText('Benchmark');
    expect(select).toHaveValue('SP500');

    // Wait for the fetched catalog to populate its options, then switch to
    // another catalog benchmark — it is sent with the build request.
    await screen.findByRole('option', {
      name: 'Dow Jones Industrial Average',
    });
    await user.selectOptions(select, 'DJIA');
    await user.click(screen.getByRole('button', { name: 'Build portfolio' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/ai-portfolio/build',
      expect.objectContaining({ benchmark: 'DJIA' }),
    );
  });
});
