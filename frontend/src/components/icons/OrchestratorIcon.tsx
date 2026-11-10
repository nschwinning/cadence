import type { SVGProps } from 'react';

/** Inline bot-orchestrator glyph (a hub directing three bots). Sized via className. */
export function OrchestratorIcon({
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
      <circle cx="12" cy="5" r="2.5" />
      <rect x="2.5" y="16" width="5" height="5" rx="1" />
      <rect x="9.5" y="16" width="5" height="5" rx="1" />
      <rect x="16.5" y="16" width="5" height="5" rx="1" />
      <path d="M12 7.5V16" />
      <path d="M12 11H5v5" />
      <path d="M12 11h7v5" />
    </svg>
  );
}

export default OrchestratorIcon;
