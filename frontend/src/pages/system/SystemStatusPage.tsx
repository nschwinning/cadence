import { useSystemStatus } from '../../api/system';
import type { SystemBackendStatus } from '../../types/api';

/** Visual treatment for a backend's reachability pill. */
function statusPill(backend: SystemBackendStatus): {
  label: string;
  className: string;
} {
  if (backend.reachable === true) {
    return {
      label: 'Reachable',
      className: 'bg-emerald-100 text-emerald-800',
    };
  }
  if (backend.reachable === false) {
    return { label: 'Unreachable', className: 'bg-red-100 text-red-800' };
  }
  // reachable === null: not probed (unconfigured, or broker stub mode).
  return {
    label: backend.configured ? 'Not probed' : 'Not configured',
    className: 'bg-slate-100 text-slate-600',
  };
}

/** Format a latency value in milliseconds, or an em dash when absent. */
function latencyLabel(latencyMs: number | null): string {
  if (latencyMs === null) return '—';
  return `${Math.round(latencyMs)} ms`;
}

/** One backend card: name + status pill, then identifier / configured / latency. */
function BackendCard({ backend }: { backend: SystemBackendStatus }) {
  const pill = statusPill(backend);
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-900">{backend.name}</h2>
        <span
          className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${pill.className}`}
        >
          {pill.label}
        </span>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Identifier
          </dt>
          <dd className="text-slate-700">{backend.identifier ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Configured
          </dt>
          <dd className="text-slate-700">{backend.configured ? 'Yes' : 'No'}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Latency
          </dt>
          <dd className="tabular-nums text-slate-700">
            {latencyLabel(backend.latency_ms)}
          </dd>
        </div>
      </dl>

      {backend.detail && (
        <p className="mt-2 text-sm text-slate-500">{backend.detail}</p>
      )}
    </div>
  );
}

/**
 * System Status — read-only view that live-probes each connected external
 * backend (broker, web search, market data, AI model) and reports whether it is
 * configured and reachable, plus the probe latency. The data is fetched on load,
 * polled for freshness, and refreshable on demand. No secret value is ever shown:
 * the backend reports only booleans and non-secret identifiers.
 */
export function SystemStatusPage() {
  const { data, isPending, isError, refetch, isFetching } = useSystemStatus();

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            System Status
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Live reachability of the connected backends. Read-only; no secrets are
            shown.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="shrink-0 rounded border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isFetching ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {isPending && (
        <p role="status" aria-live="polite" className="text-slate-500">
          Probing backends…
        </p>
      )}

      {isError && (
        <div
          role="alert"
          className="rounded border border-red-300 bg-red-50 p-4 text-red-800"
        >
          <p className="font-semibold">Could not load system status</p>
          <p className="mt-1 text-sm">Please try again later.</p>
        </div>
      )}

      {!isPending && !isError && data && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {data.backends.map((backend) => (
            <BackendCard key={backend.name} backend={backend} />
          ))}
        </div>
      )}
    </section>
  );
}

export default SystemStatusPage;
