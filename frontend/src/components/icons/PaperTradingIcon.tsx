import type { SVGProps } from 'react';

/** Inline paper-trading (document with activity line) glyph. Sized via className. */
export function PaperTradingIcon({
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
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="m8 15 2-2 2 2 3-4" />
    </svg>
  );
}

export default PaperTradingIcon;
