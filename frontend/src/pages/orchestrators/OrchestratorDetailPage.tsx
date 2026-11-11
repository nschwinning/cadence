import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ORCHESTRATOR_RUNS_PAGE_SIZE,
  isLiveRunStatus,
  useArchiveOrchestrator,
  useOrchestrator,
  useOrchestratorRuns,
  useStartOrchestratorRun,
  useStopOrchestrator,
} from '../../api/orchestrators';
import { StatTile } from '../../components/dashboard/StatTile';
import { Pagination } from '../../components/Pagination';
import { formatCurrency, formatPercent } from '../../lib/format';
import { Panel } from '../paper-trading/PaperTradingSessionPage';
import type {
  BotOrchestratorDetail,
  OrchestratorAction,
  OrchestratorBot,
  OrchestratorRunSummary,
} from '../../types/api';
import {
  CADENCE_LABELS,
  RunStatusBadge,
  StatusBadge,
  formatSignedPercent,
  signClass,
} from './orchestratorUi';

const BUTTON_CLASS =
  'rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50';

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="text-sm text-slate-900">{value}</dd>
    </div>
  );
}

/** Header with the lifecycle actions available for the orchestrator's status. */
function Header({ orchestrator }: { orchestrator: BotOrchestratorDetail }) {
  const runNow = useStartOrchestratorRun();
  const stop = useStopOrchestrator();
  const archive = useArchiveOrchestrator();
  const [confirmingStop, setConfirmingStop] = useState(false);
  const isActive = orchestrator.status === 'active';
  const runLive = isLiveRunStatus(orchestrator.last_run?.status);

  return (
    <header className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {orchestrator.label}
          </h1>
          <StatusBadge status={orchestrator.status} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isActive && (
            <button
              type="button"
              onClick={() => runNow.mutate(orchestrator.id)}
              disabled={runNow.isPending || runLive}
              className="rounded bg-emerald-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
            >
              {runLive ? 'Run in progress…' : 'Run now'}
            </button>
          )}
          {isActive && !confirmingStop && (
            <button
              type="button"
              onClick={() => setConfirmingStop(true)}
              className={BUTTON_CLASS}
            >
              Stop
            </button>
          )}
          {isActive && confirmingStop && (
            <span
              role="group"
              aria-label="Confirm stop"
              className="flex items-center gap-2 rounded border border-red-200 bg-red-50 px-2 py-1"
            >
              <span className="text-xs text-red-800">
                Stop it and sell all its bots?
              </span>
              <button
                type="button"
                onClick={() => {
                  stop.mutate(orchestrator.id);
                  setConfirmingStop(false);
                }}
                className="rounded bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700"
              >
                Confirm stop
              </button>
              <button
                type="button"
                onClick={() => setConfirmingStop(false)}
                className="text-xs text-slate-600 underline"
              >
                Cancel
              </button>
            </span>
          )}
          {orchestrator.status === 'stopped' && (
            <button
              type="button"
              onClick={() => archive.mutate(orchestrator.id)}
              disabled={archive.isPending}
              className={BUTTON_CLASS}
            >
              {archive.isPending ? 'Archiving…' : 'Archive'}
            </button>
          )}
        </div>
      </div>
      {(runNow.isError || stop.isError || archive.isError) && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {runNow.isError
            ? 'Could not start a run (a run may already be in progress).'
            : stop.isError
              ? 'Could not stop the orchestrator.'
              : 'Could not archive the orchestrator.'}
        </p>
      )}
      {runLive && (
        <p role="status" className="mt-3 text-sm text-sky-800">
          A decision run is {orchestrator.last_run?.status}… this view refreshes until it
          finishes.
        </p>
      )}
      <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Fact
          label="Cadence"
          value={`${CADENCE_LABELS[orchestrator.cadence] ?? orchestrator.cadence} · 09:00 ET`}
        />
        <Fact label="AI model" value={orchestrator.model} />
        <Fact label="Benchmark" value={orchestrator.benchmark} />
        <Fact label="Capital pool" value={formatCurrency(orchestrator.capital)} />
        <Fact label="Max parallel bots" value={String(orchestrator.max_parallel_bots)} />
        <Fact
          label="Max per bot"
          value={`${formatPercent(orchestrator.max_bot_share, 0)} of pool`}
        />
        <Fact label="Max tickers per bot" value={String(orchestrator.max_tickers_per_bot)} />
        <Fact
          label="Created"
          value={new Date(orchestrator.created_at).toLocaleString()}
        />
      </dl>
    </header>
  );
}

function CapitalTiles({ orchestrator }: { orchestrator: BotOrchestratorDetail }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
      <StatTile label="Value" value={formatCurrency(orchestrator.value)} />
      <StatTile
        label="Return"
        value={
          <span className={signClass(orchestrator.total_return_pct)}>
            {formatSignedPercent(orchestrator.total_return_pct)}
          </span>
        }
        hint={`on ${formatCurrency(orchestrator.capital)}`}
      />
      <StatTile label="Free capital" value={formatCurrency(orchestrator.free_capital)} />
      <StatTile
        label="Allocated"
        value={formatCurrency(orchestrator.allocated_capital)}
      />
      <StatTile
        label="AI cost"
        value={
          orchestrator.ai_cost_usd === null ? '—' : formatCurrency(orchestrator.ai_cost_usd)
        }
        hint={orchestrator.ai_cost_usd === null ? 'Cost tracking unavailable' : 'all time'}
      />
      <StatTile
        label="Active bots"
        value={`${orchestrator.active_bots} / ${orchestrator.max_parallel_bots}`}
        hint={
          orchestrator.liquidating_bots > 0
            ? `${orchestrator.liquidating_bots} being sold`
            : undefined
        }
      />
    </div>
  );
}

/** A bot's lifecycle as the orchestrator sees it. */
function botState(bot: OrchestratorBot): string {
  if (bot.status === 'active') return 'Active';
  if (bot.open_positions > 0) return 'Selling';
  if (bot.capital_returned_at) return 'Finished';
  return 'Stopped';
}

function BotsPanel({ bots }: { bots: OrchestratorBot[] }) {
  return (
    <Panel
      title="Bots"
      count={bots.length}
      isPending={false}
      isError={false}
      isEmpty={bots.length === 0}
      emptyText="No bots yet. The first decision run will deploy them."
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[700px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">Bot</th>
              <th className="px-4 py-3">Tickers</th>
              <th className="px-4 py-3">State</th>
              <th className="px-4 py-3 text-right">Allocated</th>
              <th className="px-4 py-3 text-right">Value</th>
              <th className="px-4 py-3 text-right">Return</th>
            </tr>
          </thead>
          <tbody>
            {bots.map((bot) => (
              <tr key={bot.id} className="border-b border-slate-100">
                <td className="px-4 py-3 font-semibold">
                  <Link
                    to={`/bots/${bot.id}`}
                    className="text-emerald-700 hover:text-emerald-800 hover:underline"
                  >
                    {bot.display_name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-slate-700">{bot.tickers.join(', ')}</td>
                <td className="px-4 py-3 text-slate-700">{botState(bot)}</td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                  {formatCurrency(bot.initial_capital)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                  {formatCurrency(bot.current_value)}
                </td>
                <td
                  className={`px-4 py-3 text-right tabular-nums font-medium ${signClass(bot.total_return_pct)}`}
                >
                  {formatSignedPercent(bot.total_return_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

/**
 * One-line description of an applied or rejected action. Applied actions carry their
 * fields directly; rejected ones nest the AI's original action under `action`.
 */
function describeAction(action: OrchestratorAction): string {
  const source = (action.action ?? action) as Record<string, unknown>;
  const preset = typeof source.preset_key === 'string' ? source.preset_key : null;
  const tickers = Array.isArray(source.tickers) ? (source.tickers as string[]) : [];
  const onTickers = tickers.length > 0 ? ` on ${tickers.join(', ')}` : '';
  if (action.kind === 'stop') {
    return `Stop ${preset ?? `bot ${String(source.bot_id ?? '')}`}${onTickers}`;
  }
  const capital = typeof source.capital === 'number' ? source.capital : null;
  const amount = capital !== null ? ` with ${formatCurrency(capital)}` : '';
  return `Deploy ${preset ?? 'unknown preset'}${onTickers}${amount}`;
}

const tokenFormatter = new Intl.NumberFormat('en-US');

/** "1,234 tokens · $0.04"; tokens are omitted without usage, cost shows "—" if unknown. */
function runUsageLabel(run: OrchestratorRunSummary): string {
  const cost = run.ai_cost_usd === null ? '—' : formatCurrency(run.ai_cost_usd);
  if (run.usage === null) return cost;
  return `${tokenFormatter.format(run.usage.total_tokens)} tokens · ${cost}`;
}

function RunRow({ run }: { run: OrchestratorRunSummary }) {
  const [open, setOpen] = useState(false);
  const hasDetail =
    Boolean(run.market_summary) ||
    run.applied.length > 0 ||
    run.rejected.length > 0 ||
    Boolean(run.error);
  return (
    <li className="border-b border-slate-100 px-4 py-3 last:border-b-0">
      <div className="flex flex-wrap items-center gap-3">
        <RunStatusBadge status={run.status} />
        <span className="text-sm text-slate-700">
          {new Date(run.created_at).toLocaleString()}
        </span>
        <span className="text-xs capitalize text-slate-500">{run.trigger}</span>
        <span className="text-xs text-slate-500">
          {run.applied.length} applied · {run.rejected.length} rejected
        </span>
        <span className="text-xs tabular-nums text-slate-500" data-testid="run-usage">
          {runUsageLabel(run)}
        </span>
        {hasDetail && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="ml-auto text-xs text-emerald-700 underline"
          >
            {open ? 'Hide details' : 'Show details'}
          </button>
        )}
      </div>
      {open && (
        <div className="mt-3 flex flex-col gap-2 text-sm">
          {run.market_summary && (
            <p className="text-slate-700">
              <span className="font-medium text-slate-900">Market: </span>
              {run.market_summary}
            </p>
          )}
          {run.error && <p className="text-red-700">{run.error}</p>}
          {run.applied.length > 0 && (
            <ul className="list-disc pl-5 text-slate-700">
              {run.applied.map((action, i) => (
                <li key={`applied-${i}`}>
                  {describeAction(action)}
                  {action.rationale || action.reason ? (
                    <span className="text-slate-500"> — {action.rationale ?? action.reason}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {run.rejected.length > 0 && (
            <ul className="list-disc pl-5 text-amber-800">
              {run.rejected.map((action, i) => (
                <li key={`rejected-${i}`}>
                  Rejected: {describeAction(action)} — {action.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

function RunsPanel({ orchestratorId, live }: { orchestratorId: string; live: boolean }) {
  const [page, setPage] = useState(0);
  const { data, isPending, isError } = useOrchestratorRuns(orchestratorId, page, live);
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  return (
    <Panel
      title="Decision runs"
      count={total}
      isPending={isPending}
      isError={isError}
      isEmpty={items.length === 0}
      emptyText="No decision runs yet. The next run happens at 09:00 ET on a trading day, or use Run now."
      footer={
        total > ORCHESTRATOR_RUNS_PAGE_SIZE ? (
          <Pagination
            page={page}
            pageSize={ORCHESTRATOR_RUNS_PAGE_SIZE}
            total={total}
            onPageChange={setPage}
            label="runs"
          />
        ) : undefined
      }
    >
      <ul>
        {items.map((run) => (
          <RunRow key={run.id} run={run} />
        ))}
      </ul>
    </Panel>
  );
}

/** One orchestrator: configuration, capital, its bots, and its decision runs. */
export function OrchestratorDetailPage() {
  const { id = '' } = useParams();
  const { data, isPending, isError } = useOrchestrator(id);

  if (isPending) {
    return (
      <p role="status" aria-live="polite" className="p-6 text-slate-500">
        Loading orchestrator…
      </p>
    );
  }
  if (isError || !data) {
    return (
      <div role="alert" className="rounded border border-red-300 bg-red-50 p-4 text-red-800">
        <p className="font-semibold">Could not load this orchestrator</p>
        <Link to="/orchestrators" className="mt-1 inline-block text-sm underline">
          Back to orchestrators
        </Link>
      </div>
    );
  }

  return (
    <section className="flex flex-col gap-6">
      <Link to="/orchestrators" className="text-sm text-emerald-700 hover:underline">
        ← Orchestrators
      </Link>
      <Header orchestrator={data} />
      <CapitalTiles orchestrator={data} />
      <BotsPanel bots={data.bots} />
      <RunsPanel orchestratorId={data.id} live={isLiveRunStatus(data.last_run?.status)} />
    </section>
  );
}

export default OrchestratorDetailPage;
