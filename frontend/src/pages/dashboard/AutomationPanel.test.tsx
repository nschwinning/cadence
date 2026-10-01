import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AutomationPanel } from './AutomationPanel';
import { makeOverview } from './fixtures';

function renderPanel(automation = makeOverview().automation) {
  return render(
    <MemoryRouter>
      <AutomationPanel automation={automation} />
    </MemoryRouter>,
  );
}

describe('AutomationPanel', () => {
  it('renders the latest run with a link to its run detail page', () => {
    renderPanel();
    expect(screen.getByText(/last rebalance/i)).toBeInTheDocument();
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/runs/run-1');
  });

  it('shows the in-flight indicator and failed-run count', () => {
    const automation = makeOverview({
      automation: {
        ...makeOverview().automation,
        in_flight: true,
        failed_in_range: 3,
      },
    }).automation;
    renderPanel(automation);
    expect(screen.getByText(/in progress/i)).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('handles no runs yet', () => {
    const automation = makeOverview({
      automation: { ...makeOverview().automation, latest_run: null },
    }).automation;
    renderPanel(automation);
    expect(screen.getByText(/No rebalance runs yet/)).toBeInTheDocument();
  });
});
