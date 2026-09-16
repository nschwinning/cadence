import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { apiClient } from './client';
import {
  isTerminalOrderStatus,
  paperTradingKeys,
  useSessionOrderSync,
} from './paperTrading';
import type { PaperTrade, PaperTradeReconcileResult } from '../types/api';

// Mock the shared axios client rather than the network.
vi.mock('./client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const mockedPost = vi.mocked(apiClient.post);

function makeTrade(orderStatus: string): PaperTrade {
  return {
    id: 'trade-1',
    session_id: 'sess-1',
    ai_portfolio_event_id: null,
    ticker: 'AAPL',
    side: 'buy',
    quantity: 5,
    price: 20,
    notional: 100,
    signal_type: 'entry',
    executed_at: '2026-09-14T00:00:00Z',
    order_id: 'o1',
    order_status: orderStatus,
    filled_price: null,
    filled_at: null,
  };
}

function makeResult(orderStatus: string): PaperTradeReconcileResult {
  return {
    trades_seen: 1,
    trades_reconciled: 1,
    trades_filled: orderStatus === 'filled' ? 1 : 0,
    trades_basis_corrected: 0,
    trades: [makeTrade(orderStatus)],
  };
}

function wrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('paperTradingKeys factory', () => {
  it('builds the order-sync key', () => {
    expect(paperTradingKeys.orderSync('sess-1')).toEqual([
      'paper-trading',
      'session',
      'sess-1',
      'order-sync',
    ]);
  });

  it('builds the kpis key', () => {
    expect(paperTradingKeys.kpis('sess-1')).toEqual([
      'paper-trading',
      'session',
      'sess-1',
      'kpis',
    ]);
  });
});

describe('isTerminalOrderStatus', () => {
  it('is true only for filled/cancelled/rejected', () => {
    expect(isTerminalOrderStatus('filled')).toBe(true);
    expect(isTerminalOrderStatus('cancelled')).toBe(true);
    expect(isTerminalOrderStatus('rejected')).toBe(true);
    expect(isTerminalOrderStatus('submitted')).toBe(false);
    expect(isTerminalOrderStatus('pending')).toBe(false);
    expect(isTerminalOrderStatus('partially_filled')).toBe(false);
  });
});

describe('useSessionOrderSync polling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('reconciles on mount, polls while non-terminal, and stops once terminal', async () => {
    let current = makeResult('submitted');
    mockedPost.mockImplementation(() => Promise.resolve({ data: current }));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });

    renderHook(() => useSessionOrderSync('sess-1'), {
      wrapper: wrapper(queryClient),
    });

    // Initial reconcile on mount.
    await vi.advanceTimersByTimeAsync(0);
    expect(mockedPost).toHaveBeenCalledTimes(1);
    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/paper-trading/sessions/sess-1/reconcile',
      {},
    );

    // Still open -> poll fires another reconcile.
    await vi.advanceTimersByTimeAsync(1500);
    expect(mockedPost).toHaveBeenCalledTimes(2);

    // Trade fills; the next poll observes the terminal status and stops.
    current = makeResult('filled');
    await vi.advanceTimersByTimeAsync(1500);
    expect(mockedPost).toHaveBeenCalledTimes(3);

    // No further polling once every trade is terminal.
    await vi.advanceTimersByTimeAsync(6000);
    expect(mockedPost).toHaveBeenCalledTimes(3);
  });

  it('does not poll when the first reconcile is already terminal', async () => {
    mockedPost.mockResolvedValue({ data: makeResult('filled') });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });

    renderHook(() => useSessionOrderSync('sess-1'), {
      wrapper: wrapper(queryClient),
    });

    await vi.advanceTimersByTimeAsync(0);
    expect(mockedPost).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(6000);
    expect(mockedPost).toHaveBeenCalledTimes(1);
  });

  it('is disabled (never reconciles) while the session id is empty', async () => {
    mockedPost.mockResolvedValue({ data: makeResult('submitted') });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });

    renderHook(() => useSessionOrderSync(''), { wrapper: wrapper(queryClient) });

    await vi.advanceTimersByTimeAsync(3000);
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('invalidates the trades query as statuses change', async () => {
    mockedPost.mockResolvedValue({ data: makeResult('submitted') });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    renderHook(() => useSessionOrderSync('sess-1'), {
      wrapper: wrapper(queryClient),
    });

    await vi.advanceTimersByTimeAsync(0);
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: paperTradingKeys.trades('sess-1'),
    });
  });
});
