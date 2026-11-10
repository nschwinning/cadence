import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { OrchestratorsPage } from './OrchestratorsPage';
import { apiClient } from '../../api/client';
import type { BotOrchestrator } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

const orchestrator: BotOrchestrator = {
  id: 'o1',
  label: 'Core rotation',
  status: 'active',
  capital: 10000,
  free_capital: 4000,
  allocated_capital: 6000,
  value: 10250,
  total_return_pct: 0.025,
  max_parallel_bots: 3,
  max_bot_share: 0.5,
  max_tickers_per_bot: 5,
  cadence: 'weekly',
  model: 'gpt-6-luna',
  benchmark: 'SP500',
  active_bots: 2,
  liquidating_bots: 0,
  created_at: '2026-11-09T14:00:00Z',
  stopped_at: null,
  archived_at: null,
  last_run: {
    id: 'r1',
    trigger: 'scheduled',
    status: 'partial',
    model: 'gpt-6-luna',
    created_at: '2026-11-10T14:00:00Z',
    started_at: '2026-11-10T14:00:01Z',
    finished_at: '2026-11-10T14:01:00Z',
    duration_ms: 59000,
    error: null,
    market_summary: 'Breadth improving.',
    applied: [],
    rejected: [],
    usage: null,
    ai_cost_usd: 0.03,
  },
  ai_cost_usd: 0.42,
};

function routeGet(items: BotOrchestrator[] = [orchestrator]) {
  return (url: string) => {
    if (url.endsWith('/models'))
      return Promise.resolve({ data: [{ id: 'gpt-6-luna', name: 'GPT-6 Luna' }] });
    if (url.endsWith('/benchmarks'))
      return Promise.resolve({ data: [{ id: 'SP500', name: 'S&P 500' }] });
    return Promise.resolve({ data: { items, total: items.length } });
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/orchestrators']}>
        <Routes>
          <Route path="/orchestrators" element={<OrchestratorsPage />} />
          <Route path="/orchestrators/:id" element={<p>Detail page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('OrchestratorsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists orchestrators with their key figures', async () => {
    mockedGet.mockImplementation(routeGet());
    renderPage();

    const link = await screen.findByRole('link', { name: 'Core rotation' });
    const row = link.closest('tr') as HTMLElement;
    expect(within(row).getByText('active')).toBeInTheDocument();
    expect(within(row).getByText('Weekly')).toBeInTheDocument();
    expect(within(row).getByText('$10,250.00')).toBeInTheDocument();
    expect(within(row).getByText('+2.50%')).toBeInTheDocument();
    expect(within(row).getByText('2 / 3')).toBeInTheDocument();
    expect(within(row).getByText('partial')).toBeInTheDocument();
    expect(within(row).getByText('$0.42')).toBeInTheDocument();
  });

  it('shows an empty state without orchestrators', async () => {
    mockedGet.mockImplementation(routeGet([]));
    renderPage();

    expect(await screen.findByText(/No orchestrators yet/)).toBeInTheDocument();
  });

  it('opens the deploy form pre-filled with the defaults', async () => {
    mockedGet.mockImplementation(routeGet());
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Deploy orchestrator' }));

    expect(screen.getByLabelText('Capital pool ($)')).toHaveValue(10000);
    expect(screen.getByLabelText('Max parallel bots')).toHaveValue(3);
    expect(screen.getByLabelText('Max per bot (% of pool)')).toHaveValue(50);
    expect(screen.getByLabelText('Max tickers per bot')).toHaveValue(5);
    expect(screen.getByLabelText('Decision cadence')).toHaveValue('daily');
  });

  it('accepts any capital amount and share (no browser step mismatch)', async () => {
    mockedGet.mockImplementation(routeGet());
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Deploy orchestrator' }));
    const capital = screen.getByLabelText('Capital pool ($)') as HTMLInputElement;
    await user.clear(capital);
    await user.type(capital, '7500.5');
    const share = screen.getByLabelText('Max per bot (% of pool)') as HTMLInputElement;
    await user.clear(share);
    await user.type(share, '33');

    expect(capital.validity.valid).toBe(true);
    expect(share.validity.valid).toBe(true);
  });

  it('blocks capital below $5,000', async () => {
    mockedGet.mockImplementation(routeGet());
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Deploy orchestrator' }));
    await user.type(screen.getByLabelText('Name'), 'Tiny');
    const capital = screen.getByLabelText('Capital pool ($)');
    await user.clear(capital);
    await user.type(capital, '4000');

    expect(capital).toHaveAttribute('aria-invalid', 'true');
    // The header button stays enabled; the form's submit is the one inside the dialog.
    const dialog = screen.getByRole('dialog');
    expect(
      within(dialog).getByRole('button', { name: 'Deploy orchestrator' }),
    ).toBeDisabled();
  });

  it('submits the request and navigates to the new orchestrator', async () => {
    mockedGet.mockImplementation(routeGet());
    mockedPost.mockResolvedValue({ data: { ...orchestrator, id: 'o2', bots: [] } });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Deploy orchestrator' }));
    await user.type(screen.getByLabelText('Name'), 'Momentum desk');
    await user.selectOptions(screen.getByLabelText('Decision cadence'), 'weekly');
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Deploy orchestrator' }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/api/v1/bot-orchestrators', {
        label: 'Momentum desk',
        capital: 10000,
        max_parallel_bots: 3,
        max_bot_share: 0.5,
        max_tickers_per_bot: 5,
        cadence: 'weekly',
        model: null,
        benchmark: 'SP500',
      });
    });
    expect(await screen.findByText('Detail page')).toBeInTheDocument();
  });
});
