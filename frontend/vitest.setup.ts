import '@testing-library/jest-dom/vitest';

// jsdom does not implement PointerEvent. The charts use pointer events for hover
// inspection; aliasing PointerEvent to MouseEvent lets `fireEvent.pointerMove`
// carry clientX/clientY so hover hit-testing can be exercised in tests.
if (typeof window !== 'undefined' && typeof window.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {}
  window.PointerEvent = PointerEventPolyfill as unknown as typeof PointerEvent;
  globalThis.PointerEvent = PointerEventPolyfill as unknown as typeof PointerEvent;
}
