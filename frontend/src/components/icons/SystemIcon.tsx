import type { SVGProps } from 'react';

/** Inline server / system-status glyph. Sized via className. */
export function SystemIcon({
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
      <rect x="3" y="4" width="18" height="6" rx="1" />
      <rect x="3" y="14" width="18" height="6" rx="1" />
      <path d="M7 7h.01" />
      <path d="M7 17h.01" />
    </svg>
  );
}

export default SystemIcon;
