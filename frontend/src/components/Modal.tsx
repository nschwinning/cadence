import { useEffect, useRef } from 'react';

/**
 * A small reusable, accessible modal dialog.
 *
 * Renders nothing when `open` is false. When open it mounts a centered panel
 * over a dimmed backdrop and labels the dialog with `title` (its accessible
 * name). It closes via the × control, a backdrop click, or the Escape key, each
 * routed through `onClose`; the caller owns the `open` state so the dialog only
 * dismisses when the caller chooses to. The panel is transparent chrome — the
 * caller supplies its own card as `children`.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);

  // While open, close on Escape and move focus into the dialog so keyboard
  // users land inside it rather than on the page behind the backdrop.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    dialogRef.current?.focus();
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 sm:items-center"
      // Close only when the backdrop itself is pressed, not when a press that
      // started inside the panel bubbles up here.
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="relative my-8 w-full max-w-3xl focus:outline-none"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-3 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-full text-xl leading-none text-slate-500 hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        >
          <span aria-hidden="true">×</span>
        </button>
        {children}
      </div>
    </div>
  );
}

export default Modal;
