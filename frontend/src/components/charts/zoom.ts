/**
 * Shared zoom configuration for the value charts (paper-trading session + comparison,
 * dashboard combined equity, bot value). Adds two complementary interactions:
 *
 *  - a horizontal **range-selector slider** under the plot, plus mouse-wheel /
 *    drag-to-pan ("inside") zoom, both on the x-axis, via `dataZoom`; and
 *  - a **rubber-band box-select** zoom button and a reset button, via the toolbox
 *    `dataZoom` feature.
 *
 * The slider and wheel/drag navigate the time (x) axis only, so the y-axis
 * auto-rescales to the visible window. The box-select, by contrast, zooms **both**
 * axes: dragging a rectangle zooms to exactly that region (time span and value
 * range), and the drawn selection is the region itself rather than a full-height
 * band — so the box never obscures the curve while you drag it. The reset button
 * restores the full range on every axis. Pair `ZOOM_GRID` with these so the slider
 * (bottom) and toolbar (top-right) do not overlap the axis labels — it widens the
 * default grid insets accordingly.
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

/**
 * Rubber-band box-select zoom (both axes) and a reset-zoom button. Omitting
 * `yAxisIndex` lets a dragged box zoom the time span and the value range together,
 * so the selection rectangle is exactly the region drawn (not a full-height band).
 */
export const ZOOM_TOOLBOX: ToolboxComponentOption = {
  right: 8,
  top: 0,
  feature: {
    dataZoom: {
      title: { zoom: 'Box zoom', back: 'Undo box zoom' },
    },
    restore: { title: 'Reset zoom' },
  },
};
