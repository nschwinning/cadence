import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { apiClient } from './client';
import {
  aiPortfolioKeys,
  isTerminalEventStatus,
  useBuildStatus,
} from './aiPortfolio';
import type { AIEventStatus, AIPortfolioEvent } from '../types/api';

// Mock the shared axios client rather than the network.
vi.mock('./client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const mockedGet = vi.mocked(apiClient.get);

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

function wrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('aiPortfolioKeys factory', () => {
  it('builds hierarchical keys', () => {
    expect(aiPortfolioKeys.all).toEqual(['ai-portfolio']);
    expect(aiPortfolioKeys.buildStatus('evt-1')).toEqual([
      'ai-portfolio',
      'build-status',
      'evt-1',
    ]);
    expect(aiPortfolioKeys.sessionEvents('sess-1')).toEqual([
      'ai-portfolio',
      'session',
      'sess-1',
      'events',
    ]);
  });
});

describe('isTerminalEventStatus', () => {
  it('is true only for succeeded/partial/failed/skipped', () => {
    expect(isTerminalEventStatus('succeeded')).toBe(true);
    expect(isTerminalEventStatus('partial')).toBe(true);
    expect(isTerminalEventStatus('failed')).toBe(true);
    expect(isTerminalEventStatus('skipped')).toBe(true);
    expect(isTerminalEventStatus('queued')).toBe(false);
    expect(isTerminalEventStatus('running')).toBe(false);
  });
});

describe('useBuildStatus polling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('polls while non-terminal and stops once terminal', async () => {
    let current = makeEvent('running');
    mockedGet.mockImplementation(() => Promise.resolve({ data: current }));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });

    renderHook(() => useBuildStatus('evt-1'), { wrapper: wrapper(queryClient) });

    // Initial fetch.
    await vi.advanceTimersByTimeAsync(0);
    expect(mockedGet).toHaveBeenCalledTimes(1);

    // Still running -> poll fires another fetch.
    await vi.advanceTimersByTimeAsync(1500);
    expect(mockedGet).toHaveBeenCalledTimes(2);

    // Reaches a terminal status; next poll observes it and stops.
    current = makeEvent('succeeded');
    await vi.advanceTimersByTimeAsync(1500);
    expect(mockedGet).toHaveBeenCalledTimes(3);

    // No further polling once terminal.
    await vi.advanceTimersByTimeAsync(6000);
    expect(mockedGet).toHaveBeenCalledTimes(3);
  });

  it('is disabled (never fetches) while the id is null', async () => {
    mockedGet.mockResolvedValue({ data: makeEvent('running') });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });

    renderHook(() => useBuildStatus(null), { wrapper: wrapper(queryClient) });

    await vi.advanceTimersByTimeAsync(3000);
    expect(mockedGet).not.toHaveBeenCalled();
  });
});
