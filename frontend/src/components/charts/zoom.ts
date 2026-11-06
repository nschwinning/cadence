/**
 * Shared zoom configuration for the value charts (paper-trading session + comparison,
 * dashboard combined equity, bot value). Adds two complementary interactions:
 *
 *  - a horizontal **range-selector slider** under the plot, plus mouse-wheel /
 *    drag-to-pan ("inside") zoom, via `dataZoom`; and
 *  - a **rubber-band box-select** zoom button and a reset button, via the toolbox
 *    `dataZoom` feature.
 *
 * All of these zoom the x-axis only (`yAxisIndex: 'none'` on the box-select), so the
 * y-axis auto-rescales to the visible window. Pair `ZOOM_GRID` with these so the
 * slider (bottom) and toolbar (top-right) do not overlap the axis labels — it widens
 * the default grid insets accordingly.
 *
 * These consts are inert under test (the chart tests mock the `EChart` wrapper and
 * inspect the option JSON); the `EChart` wrapper preserves the zoom window across
 * option updates so a periodic refetch does not reset the user's selection.
 */
import type {
  DataZoomComponentOption,
  GridComponentOption,
  ToolboxComponentOption,
} from 'echarts/components';

/** Grid insets leaving room for the bottom slider and the top-right toolbar. */
export const ZOOM_GRID: GridComponentOption = {
  left: 64,
  right: 16,
  top: 28,
  bottom: 56,
};

/** Wheel/drag zoom plus a draggable range-selector slider, both on the x-axis. */
export const ZOOM_DATA_ZOOM: DataZoomComponentOption[] = [
  { type: 'inside', zoomOnMouseWheel: true, moveOnMouseMove: true },
  { type: 'slider', height: 18, bottom: 8 },
];

/** Rubber-band box-select zoom (x-axis only) and a reset-zoom button. */
export const ZOOM_TOOLBOX: ToolboxComponentOption = {
  right: 8,
  top: 0,
  feature: {
    dataZoom: {
      yAxisIndex: 'none',
      title: { zoom: 'Box zoom', back: 'Undo box zoom' },
    },
    restore: { title: 'Reset zoom' },
  },
};
