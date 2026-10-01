import type { SVGProps } from 'react';

/** Inline candlestick / indicator-chart glyph. Sized via className. */
export function TechnicalIndicatorsIcon({
  className = 'h-5 w-5',
  ...props
}: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      {...props}
    >
      <path d="M3 3v18h18" />
      <path d="M7 14l3-3 3 3 5-5" />
    </svg>
  );
}

export default TechnicalIndicatorsIcon;
