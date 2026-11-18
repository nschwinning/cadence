import { useEffect, useState } from 'react';
import { FORBIDDEN_EVENT } from './session';

/** A dismissible notice shown when the API refuses an action for missing permissions. */
export function PermissionBanner() {
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const show = (event: Event) => {
      const detail = (event as CustomEvent<string | undefined>).detail;
      setMessage(detail || "You don't have permission for this action");
    };
    window.addEventListener(FORBIDDEN_EVENT, show);
    return () => window.removeEventListener(FORBIDDEN_EVENT, show);
  }, []);

  if (!message) return null;
  return (
    <div
      role="alert"
      className="mb-4 flex items-start justify-between gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
    >
      <span>{message}</span>
      <button
        type="button"
        onClick={() => setMessage(null)}
        aria-label="Dismiss"
        className="font-semibold text-amber-900 hover:text-amber-700"
      >
        ×
      </button>
    </div>
  );
}
