import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  DataZoomComponent,
  ToolboxComponent,
} from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';
import type { EChartsCoreOption } from 'echarts/core';

// Register only the pieces the paper-trading charts use, so the bundle tree-shakes
// the rest of ECharts away. The SVG renderer (rather than canvas) keeps the output
// as inspectable DOM — crisp text and testable in jsdom, which has no canvas.
// DataZoom (slider + inside wheel/drag) and Toolbox (rubber-band box-select + reset)
// power the charts' zoom controls — see `components/charts/zoom.ts`.
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  DataZoomComponent,
  ToolboxComponent,
  SVGRenderer,
]);

/** Fallback width used when the container reports no measured width (e.g. jsdom). */
const FALLBACK_WIDTH = 600;

/**
 * Thin React wrapper around an Apache ECharts instance. Integrates `echarts` core
 * directly (rather than `echarts-for-react`, which lags React 19 peer deps): it owns
 * a container `div`, initialises one chart with the SVG renderer, pushes each new
 * `option` with `notMerge` so stale series never linger, resizes with the container,
 * and disposes on unmount. The container carries `role="img"` + `ariaLabel` so it is
 * discoverable by its accessible name.
 */
export function EChart({
  option,
  height = 200,
  className,
  ariaLabel,
}: {
  option: EChartsCoreOption;
  height?: number;
  className?: string;
  ariaLabel?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, {
      renderer: 'svg',
      width: el.clientWidth || FALLBACK_WIDTH,
      height,
    });
    chartRef.current = chart;

    // jsdom has no ResizeObserver; guard so the chart still mounts under test.
    let observer: ResizeObserver | undefined;
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => {
        chart.resize({ width: el.clientWidth || FALLBACK_WIDTH, height });
      });
      observer.observe(el);
    }

    return () => {
      observer?.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    // Preserve any active zoom window across the notMerge replace below, so a
    // periodic refetch (e.g. the dashboard's 30s poll) or an option recompute does
    // not snap the user's zoom back to the full range. dataZoom start/end are
    // percentages, so they remain valid as the underlying data updates.
    const prev = chart.getOption() as
      | { dataZoom?: Array<{ start?: number; end?: number }> }
      | undefined;
    const savedZoom = prev?.dataZoom?.map((z) => ({
      start: z.start,
      end: z.end,
    }));
    chart.setOption(option, { notMerge: true });
    if (savedZoom && savedZoom.length > 0) {
      chart.setOption({ dataZoom: savedZoom }, { lazyUpdate: true });
    }
  }, [option]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ height }}
      role="img"
      aria-label={ariaLabel}
    />
  );
}

export default EChart;
