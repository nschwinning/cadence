import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { AiCostBreakdown } from './AiCostBreakdown';
import { makeAiCosts } from '../../pages/dashboard/fixtures';

describe('AiCostBreakdown', () => {
  it('renders one row per portfolio sorted by cost descending with a total', () => {
    render(
      <AiCostBreakdown
        data={makeAiCosts({
          portfolios: [
            { session_id: 'low', label: 'Laggard', ai_cost_usd: 2 },
            { session_id: 'high', label: 'Leader', ai_cost_usd: 7.5 },
          ],
          total_ai_cost_usd: 9.5,
        })}
      />,
    );

    const rows = screen.getAllByRole('row');
    // header + 2 body rows + total row
    const bodyLabels = screen
      .getAllByRole('cell')
      .filter((c) => ['Laggard', 'Leader'].includes(c.textContent ?? ''));
    expect(bodyLabels).toHaveLength(2);
    // Leader (higher cost) appears before Laggard.
    const leaderIndex = rows.findIndex((r) => within(r).queryByText('Leader'));
    const laggardIndex = rows.findIndex((r) => within(r).queryByText('Laggard'));
    expect(leaderIndex).toBeLessThan(laggardIndex);
    expect(screen.getByText('$7.50')).toBeInTheDocument();
    expect(screen.getByText('$2.00')).toBeInTheDocument();
    // Grand total.
    const totalRow = rows.find((r) => within(r).queryByText('Total'));
    expect(totalRow).toBeDefined();
    expect(within(totalRow!).getByText('$9.50')).toBeInTheDocument();
  });

  it('shows $0.00 for a readable zero cost', () => {
    render(
      <AiCostBreakdown
        data={makeAiCosts({
          portfolios: [
            { session_id: 'z', label: 'Quiet', ai_cost_usd: 0 },
          ],
          total_ai_cost_usd: 0,
        })}
      />,
    );
    // Both the row and the total read $0.00 (two occurrences), not an em dash.
    expect(screen.getAllByText('$0.00')).toHaveLength(2);
    expect(screen.queryByText('—')).not.toBeInTheDocument();
  });

  it('degrades to an em dash with a hint when the source is unavailable', () => {
    render(
      <AiCostBreakdown
        data={makeAiCosts({
          portfolios: [
            { session_id: 'a', label: 'Portfolio A', ai_cost_usd: null },
          ],
          total_ai_cost_usd: null,
        })}
      />,
    );
    expect(screen.getByText('Cost tracking unavailable')).toBeInTheDocument();
    // The row cost and the total both render as em dashes.
    expect(screen.getAllByText('—')).toHaveLength(2);
  });

  it('shows an empty state when there are no portfolios', () => {
    render(
      <AiCostBreakdown
        data={makeAiCosts({ portfolios: [], total_ai_cost_usd: 0 })}
      />,
    );
    expect(screen.getByText(/No active portfolios yet/i)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});
