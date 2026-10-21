import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { apiClient } from './client';
import { useDashboardOverview } from './dashboard';

// Mock the shared axios client rather than the network.
vi.mock('./client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

function wrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useDashboardOverview live ~30s refresh', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('refetches the overview once per ~30s without a storm', async () => {
    mockedGet.mockResolvedValue({ data: {} });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });

    renderHook(() => useDashboardOverview('1M'), {
      wrapper: wrapper(queryClient),
    });

    // Initial fetch on mount.
    await vi.advanceTimersByTimeAsync(0);
    expect(mockedGet).toHaveBeenCalledTimes(1);

    // Nothing fires before the interval elapses (no storm).
    await vi.advanceTimersByTimeAsync(29_000);
    expect(mockedGet).toHaveBeenCalledTimes(1);

    // One refetch at ~30s, then one more at ~60s.
    await vi.advanceTimersByTimeAsync(1_000);
    expect(mockedGet).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(mockedGet).toHaveBeenCalledTimes(3);
  });
});
