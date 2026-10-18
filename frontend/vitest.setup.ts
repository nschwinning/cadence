import '@testing-library/jest-dom/vitest';

// jsdom does not implement the canvas 2D context. ECharts (via zrender) only needs
// it to measure text width for layout; stub a minimal context so the SVG renderer
// runs under test without the noisy "HTMLCanvasElement.prototype.getContext not
// implemented" errors. `measureText` returns an approximate width; the rest are
// no-ops, which is enough for layout maths the tests do not assert on pixel-exactly.
if (typeof HTMLCanvasElement !== 'undefined') {
  const stubContext = {
    measureText: (text: string) => ({ width: String(text).length * 8 }),
  };
  HTMLCanvasElement.prototype.getContext = (() =>
    stubContext) as unknown as HTMLCanvasElement['getContext'];
}

// jsdom does not implement PointerEvent. The charts use pointer events for hover
// inspection; aliasing PointerEvent to MouseEvent lets `fireEvent.pointerMove`
// carry clientX/clientY so hover hit-testing can be exercised in tests.
if (typeof window !== 'undefined' && typeof window.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {}
  window.PointerEvent = PointerEventPolyfill as unknown as typeof PointerEvent;
  globalThis.PointerEvent = PointerEventPolyfill as unknown as typeof PointerEvent;
}
