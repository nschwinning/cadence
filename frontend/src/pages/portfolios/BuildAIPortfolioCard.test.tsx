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

  it('starts a build submitting only capital, risk profile, and rebalancing, and updates to succeeded without manual refresh', async () => {
    let status: AIEventStatus = 'running';
    mockedPost.mockResolvedValue({ data: { event_id: 'evt-1', status: 'queued' } });
    mockedGet.mockImplementation(() => Promise.resolve({ data: makeEvent(status) }));
    const user = userEvent.setup();

    const { queryClient } = renderWithClient(<BuildAIPortfolioCard />);

    await user.click(screen.getByRole('button', { name: 'Build portfolio' }));

    // Running mode appears from the polled status, no user action needed.
    expect(await screen.findByText('Building portfolio…')).toBeInTheDocument();
    expect(mockedPost).toHaveBeenCalledWith('/api/v1/ai-portfolio/build', {
      allocated_capital: 100000,
      risk_profile: 'balanced',
      daily_rebalancing: false,
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
    mockedGet.mockResolvedValue({ data: makeEvent('running') });
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
});
