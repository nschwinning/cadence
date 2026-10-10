import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { UniverseEvaluationPanel } from './UniverseEvaluationPanel';
import { apiClient } from '../../api/client';
import type { AssetUniverseEvaluation } from '../../types/api';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

const EVALUATION: AssetUniverseEvaluation = {
  narrative: 'The universe is broadly diversified.\n\nTechnology dominates.',
  strengths: ['Broad sector coverage'],
  concerns: ['Heavy technology concentration'],
  suggestions: ['Add utilities exposure'],
  generated_at: new Date().toISOString(),
  outdated: false,
};

describe('UniverseEvaluationPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the narrative, findings, and generated time', async () => {
    mockedGet.mockResolvedValue({ data: { evaluation: EVALUATION } });

    renderWithClient(<UniverseEvaluationPanel />);

    expect(
      await screen.findByText('The universe is broadly diversified.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Technology dominates.')).toBeInTheDocument();
    expect(screen.getByText('Broad sector coverage')).toBeInTheDocument();
    expect(
      screen.getByText('Heavy technology concentration'),
    ).toBeInTheDocument();
    expect(screen.getByText('Add utilities exposure')).toBeInTheDocument();
    expect(screen.getByText(/Generated/)).toBeInTheDocument();
  });

  it('shows the outdated badge only when the evaluation is outdated', async () => {
    mockedGet.mockResolvedValue({
      data: { evaluation: { ...EVALUATION, outdated: true } },
    });

    renderWithClient(<UniverseEvaluationPanel />);

    expect(await screen.findByText(/Outdated/)).toBeInTheDocument();
  });

  it('does not show the outdated badge when current', async () => {
    mockedGet.mockResolvedValue({ data: { evaluation: EVALUATION } });

    renderWithClient(<UniverseEvaluationPanel />);

    await screen.findByText('Technology dominates.');
    expect(screen.queryByText(/Outdated/)).not.toBeInTheDocument();
  });

  it('shows a generating state on first load', async () => {
    let resolve: ((value: { data: unknown }) => void) | undefined;
    mockedGet.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );

    renderWithClient(<UniverseEvaluationPanel />);

    expect(
      await screen.findByText(/Generating the universe evaluation/),
    ).toBeInTheDocument();

    resolve?.({ data: { evaluation: EVALUATION } });
    await screen.findByText('Technology dominates.');
  });

  it('refresh button triggers regeneration and shows a loading state', async () => {
    const user = userEvent.setup();
    mockedGet.mockResolvedValue({ data: { evaluation: EVALUATION } });
    let resolvePost: ((value: { data: unknown }) => void) | undefined;
    mockedPost.mockReturnValue(
      new Promise((r) => {
        resolvePost = r;
      }),
    );

    renderWithClient(<UniverseEvaluationPanel />);
    await screen.findByText('Technology dominates.');

    await user.click(screen.getByRole('button', { name: /Refresh/ }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/assets/universe-evaluation/refresh',
    );
    expect(await screen.findByText(/Refreshing/)).toBeInTheDocument();

    const refreshed: AssetUniverseEvaluation = {
      ...EVALUATION,
      narrative: 'A fresh assessment.',
    };
    resolvePost?.({ data: { evaluation: refreshed } });
    await waitFor(() =>
      expect(screen.getByText('A fresh assessment.')).toBeInTheDocument(),
    );
  });

  it('shows a message when the universe is empty', async () => {
    mockedGet.mockResolvedValue({ data: { evaluation: null } });

    renderWithClient(<UniverseEvaluationPanel />);

    expect(
      await screen.findByText(/Add assets to the universe/),
    ).toBeInTheDocument();
  });

  it('shows an error state when generation fails', async () => {
    mockedGet.mockRejectedValue(new Error('boom'));

    renderWithClient(<UniverseEvaluationPanel />);

    expect(
      await screen.findByText(/Could not generate the universe evaluation/),
    ).toBeInTheDocument();
  });

  it('is expanded by default and collapses/expands via the toggle', async () => {
    const user = userEvent.setup();
    mockedGet.mockResolvedValue({ data: { evaluation: EVALUATION } });

    renderWithClient(<UniverseEvaluationPanel />);

    // Body visible by default, toggle reports expanded.
    await screen.findByText('Technology dominates.');
    const toggle = screen.getByRole('button', { name: /Hide/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    // Collapsing hides the body; header/Refresh stay visible.
    await user.click(toggle);
    expect(screen.queryByText('Technology dominates.')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Refresh/ }),
    ).toBeInTheDocument();
    const collapsedToggle = screen.getByRole('button', { name: /Show/ });
    expect(collapsedToggle).toHaveAttribute('aria-expanded', 'false');

    // Expanding shows the body again.
    await user.click(collapsedToggle);
    expect(screen.getByText('Technology dominates.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Hide/ }),
    ).toHaveAttribute('aria-expanded', 'true');
  });
});
