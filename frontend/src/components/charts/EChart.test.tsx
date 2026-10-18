import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { EChart } from './EChart';

const option = {
  xAxis: { type: 'time' as const },
  yAxis: { type: 'value' as const },
  series: [
    {
      type: 'line' as const,
      showSymbol: false,
      data: [
        [Date.parse('2026-01-04'), 100],
        [Date.parse('2026-01-05'), 110],
      ],
    },
  ],
};

describe('EChart', () => {
  it('mounts and renders an SVG with the given accessible name', () => {
    const { getByRole, container } = render(
      <EChart option={option} ariaLabel="Test chart" />,
    );
    // The container exposes its accessible name and ECharts' SVG renderer draws
    // real DOM (no canvas), so an <svg> node is present under it.
    expect(getByRole('img', { name: 'Test chart' })).toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('does not throw when the option updates', () => {
    const { rerender, container } = render(<EChart option={option} />);
    const next = {
      ...option,
      series: [{ ...option.series[0], data: [[Date.parse('2026-01-06'), 120]] }],
    };
    expect(() => rerender(<EChart option={next} />)).not.toThrow();
    expect(container.querySelector('svg')).not.toBeNull();
  });
});
