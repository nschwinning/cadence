import type { SVGProps } from 'react';

/** Inline assets (trending line + axes) glyph. Sized via className. */
export function AssetsIcon({
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
      <path d="m7 14 3-3 3 3 5-6" />
      <path d="M18 8h3v3" />
    </svg>
  );
}

export default AssetsIcon;
