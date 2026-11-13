import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EnvironmentBadge } from './EnvironmentBadge';
import { apiClient } from '../../api/client';
import type { EnvironmentStatus } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);

function env(overrides: Partial<EnvironmentStatus> = {}): EnvironmentStatus {
  return {
    environment: 'QA',
    configured_mode: 'paper',
    account_mode: 'paper',
    mismatch: false,
    trading_enabled: true,
    reason: null,
    ...overrides,
  };
}

async function renderBadge(status: EnvironmentStatus) {
  mockedGet.mockResolvedValue({ data: status });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <EnvironmentBadge />
    </QueryClientProvider>,
  );
  return screen.findByTestId('environment-badge');
}

describe('EnvironmentBadge', () => {
  beforeEach(() => mockedGet.mockReset());

  it('shows a neutral QA · Paper badge', async () => {
    const badge = await renderBadge(env());
    expect(mockedGet).toHaveBeenCalledWith('/api/v1/system/environment');
    expect(badge).toHaveTextContent('QA · Paper');
    expect(badge.className).toContain('bg-slate-100');
  });

  it('shows a solid red PRD · Live badge when trading real money', async () => {
    const badge = await renderBadge(
      env({ environment: 'PRD', configured_mode: 'live', account_mode: 'live' }),
    );
    expect(badge).toHaveTextContent('PRD · Live');
    expect(badge.className).toContain('bg-red-600');
    expect(badge).not.toHaveTextContent('⚠');
  });

  it('shows an amber warning, not red, on a mismatch', async () => {
    const badge = await renderBadge(
      env({
        account_mode: 'live',
        mismatch: true,
        trading_enabled: false,
        reason: 'The credentials belong to a live account',
      }),
    );
    expect(badge).toHaveTextContent('⚠Account mismatch — trading blocked');
    expect(badge.className).toContain('bg-amber-100');
    expect(badge.className).not.toContain('bg-red-600');
    expect(badge).toHaveAttribute('title', 'The credentials belong to a live account');
  });

  it('shows an amber warning when live trading lacks the opt-in', async () => {
    const badge = await renderBadge(
      env({
        environment: 'PRD',
        configured_mode: 'live',
        account_mode: 'live',
        trading_enabled: false,
        reason: 'Live account: set ALPACA_ALLOW_LIVE=true',
      }),
    );
    expect(badge).toHaveTextContent('Live — trading disabled');
    expect(badge.className).toContain('bg-amber-100');
  });

  it('shows the name with account unknown while the account cannot be verified', async () => {
    const badge = await renderBadge(env({ account_mode: 'unknown' }));
    expect(badge).toHaveTextContent('QA · account unknown');
    expect(badge.className).toContain('ring-slate-400');
  });
});
