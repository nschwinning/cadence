import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { RecommendAssetsCard } from './RecommendAssetsCard';
import { apiClient } from '../../api/client';

vi.mock('../../api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

const MODELS = [
  { id: 'gpt-5-mini', name: 'GPT-5 Mini' },
  { id: 'gpt-5.6-luna', name: 'GPT-5.6 Luna' },
  { id: 'claude-opus-5-5', name: 'Claude Opus 5.5' },
];

/** Route the model-catalog GET; anything else resolves empty. */
function routeGet(url: string) {
  if (url.endsWith('/paper-trading/models')) {
    return Promise.resolve({ data: MODELS });
  }
  return Promise.resolve({ data: null });
}

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('RecommendAssetsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers only stock and crypto as category choices', () => {
    renderWithClient(<RecommendAssetsCard />);

    const chips = screen.getAllByRole('checkbox');
    const labels = chips.map((chip) => chip.textContent?.trim());

    expect(labels).toEqual(['Stock', 'Crypto']);
    expect(labels).not.toContain('ETF');
    expect(labels).not.toContain('Fund');
    expect(labels).not.toContain('Other');
  });

  it('defaults the model to the configured default and submits the selected model', async () => {
    mockedGet.mockImplementation(routeGet);
    mockedPost.mockResolvedValue({ data: { id: 1 } });
    const user = userEvent.setup();

    renderWithClient(<RecommendAssetsCard />);

    // The selector defaults to the configured default recommender model.
    const select = await screen.findByLabelText('AI model');
    expect(select).toHaveValue('gpt-5-mini');

    // Pick a category (required to submit), wait for the fetched catalog, then
    // switch models and submit — the chosen model id is sent with the request.
    await user.click(screen.getByRole('checkbox', { name: 'Stock' }));
    await screen.findByRole('option', { name: 'Claude Opus 5.5' });
    await user.selectOptions(select, 'claude-opus-5-5');
    await user.click(screen.getByRole('button', { name: 'Recommend' }));

    expect(mockedPost).toHaveBeenCalledWith(
      '/api/v1/recommendations',
      expect.objectContaining({ model: 'claude-opus-5-5' }),
    );
  });
});
