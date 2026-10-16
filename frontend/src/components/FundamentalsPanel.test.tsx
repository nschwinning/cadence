import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FundamentalsPanel } from './FundamentalsPanel';
import type { AssetFundamentals } from '../types/api';

function available(
  overrides: Partial<AssetFundamentals> = {},
): AssetFundamentals {
  return {
    source: 'sec-edgar',
    status: 'available',
    cik: '0000320193',
    document: {
      figures: {
        revenue: { value: 1_000_000_000, period_end: '2025-12-31' },
        net_income: { value: 250_000_000, period_end: '2025-12-31' },
      },
      company_details: { sicDescription: 'Software' },
    },
    fetched_at: '2026-10-15T00:00:00Z',
    ...overrides,
  };
}

describe('FundamentalsPanel', () => {
  it('renders figures with a revenue margin and company details', () => {
    render(<FundamentalsPanel fundamentals={available()} />);

    expect(screen.getByText('Revenue')).toBeInTheDocument();
    expect(screen.getByText('$1.0B')).toBeInTheDocument();
    // Net income margin vs revenue: 250M / 1B = 25.0%.
    expect(screen.getByText('25.0%')).toBeInTheDocument();
    expect(screen.getByText('Software')).toBeInTheDocument();
  });

  it('renders the unavailable note when EDGAR had nothing', () => {
    render(
      <FundamentalsPanel
        fundamentals={available({ status: 'unavailable', document: {} })}
      />,
    );

    expect(screen.getByText(/Fundamentals unavailable/)).toBeInTheDocument();
  });

  it('renders a no-record note when fundamentals are absent', () => {
    render(<FundamentalsPanel fundamentals={null} />);

    expect(
      screen.getByText('No fundamentals on record for this asset.'),
    ).toBeInTheDocument();
  });
});
