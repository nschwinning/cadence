import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useOrchestrators } from '../../api/orchestrators';
import { Modal } from '../../components/Modal';
import { formatCurrency } from '../../lib/format';
import type { BotOrchestrator } from '../../types/api';
import { DeployOrchestratorCard } from './DeployOrchestratorCard';
import { PresetCatalogPanel } from './PresetCatalogPanel';
import {
  CADENCE_LABELS,
  RunStatusBadge,
  StatusBadge,
  formatSignedPercent,
  signClass,
} from './orchestratorUi';

function OrchestratorRow({ orchestrator }: { orchestrator: BotOrchestrator }) {
  const run = orchestrator.last_run;
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3 font-semibold">
        <Link
          to={`/orchestrators/${orchestrator.id}`}
          className="text-emerald-700 hover:text-emerald-800 hover:underline"
        >
          {orchestrator.label}
        </Link>
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={orchestrator.status} />
      </td>
      <td className="px-4 py-3 text-slate-700">
        {CADENCE_LABELS[orchestrator.cadence] ?? orchestrator.cadence}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {formatCurrency(orchestrator.value)}
      </td>
      <td
        className={`px-4 py-3 text-right tabular-nums font-medium ${signClass(orchestrator.total_return_pct)}`}
      >
        {formatSignedPercent(orchestrator.total_return_pct)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {orchestrator.active_bots} / {orchestrator.max_parallel_bots}
      </td>
      <td
        className={`px-4 py-3 text-right tabular-nums ${
          orchestrator.ai_cost_usd === null ? 'text-slate-400' : 'text-slate-700'
        }`}
      >
        {orchestrator.ai_cost_usd === null ? '—' : formatCurrency(orchestrator.ai_cost_usd)}
      </td>
      <td className="px-4 py-3 text-slate-600">
        {run ? (
          <span className="inline-flex items-center gap-2">
            <RunStatusBadge status={run.status} />
            <span className="text-xs text-slate-500">
              {new Date(run.created_at).toLocaleString()}
            </span>
          </span>
        ) : (
          <span className="text-slate-400">No runs yet</span>
        )}
      </td>
    </tr>
  );
}

/** The orchestrator list with its "Deploy orchestrator" modal. */
export function OrchestratorsPage() {
  const [showArchived, setShowArchived] = useState(false);
  const [deployOpen, setDeployOpen] = useState(false);
  const { data, isPending, isError } = useOrchestrators(showArchived);
  const items = data?.items ?? [];

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Orchestrators</h1>
        <button
          type="button"
          onClick={() => setDeployOpen(true)}
          className="rounded bg-emerald-500 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
        >
          Deploy orchestrator
        </button>
      </div>

      <Modal
        open={deployOpen}
        onClose={() => setDeployOpen(false)}
        title="Deploy an orchestrator"
      >
        <DeployOrchestratorCard />
      </Modal>

      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-3 border-b border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">Orchestrators</h2>
          {!isPending && !isError && items.length > 0 && (
            <span className="text-sm text-slate-500">{data?.total} total</span>
          )}
          <label className="ml-auto flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Show archived
          </label>
        </div>

        {isPending && (
          <p role="status" aria-live="polite" className="p-6 text-slate-500">
            Loading orchestrators…
          </p>
        )}
        {isError && (
          <div
            role="alert"
            className="m-4 rounded border border-red-300 bg-red-50 p-4 text-red-800"
          >
            <p className="font-semibold">Could not load orchestrators</p>
            <p className="mt-1 text-sm">Please try again later.</p>
          </div>
        )}
        {!isPending && !isError && items.length === 0 && (
          <p className="p-6 text-slate-500">
            No orchestrators yet. Use “Deploy orchestrator” to let the AI run a set of
            preset bots for you.
          </p>
        )}
        {!isPending && !isError && items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Orchestrator</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Cadence</th>
                  <th className="px-4 py-3 text-right">Value</th>
                  <th className="px-4 py-3 text-right">Return</th>
                  <th className="px-4 py-3 text-right">Bots</th>
                  <th className="px-4 py-3 text-right">AI cost</th>
                  <th className="px-4 py-3">Last run</th>
                </tr>
              </thead>
              <tbody>
                {items.map((o) => (
                  <OrchestratorRow key={o.id} orchestrator={o} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <PresetCatalogPanel />
    </section>
  );
}

export default OrchestratorsPage;
