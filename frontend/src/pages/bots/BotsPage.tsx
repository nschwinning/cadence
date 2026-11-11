import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useBotSessions, useStrategies } from '../../api/bots';
import type { BotSession } from '../../types/api';
import { formatAge, formatCurrency } from '../../lib/format';
import { BuildBotCard } from './BuildBotCard';
import { Modal } from '../../components/Modal';

/** Status pill colors per bot status. */
const STATUS_STYLES: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-800',
  stopped: 'bg-slate-100 text-slate-700',
  archived: 'bg-slate-100 text-slate-500',
};

/** Muted gain/loss colour for a signed numeric cell. */
function signClass(value: number): string {
  if (value > 0) return 'text-emerald-700';
  if (value < 0) return 'text-red-700';
  return 'text-slate-700';
}

function StatusBadge({ status }: { status: string }) {
  const className = STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-700';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${className}`}
    >
      {status}
    </span>
  );
}

/** Compact summary of a bot's traded symbol set: `AAPL`, `AAPL +2`, or a count. */
function symbolsSummary(bot: BotSession): string {
  const tickers = bot.symbols.map((s) => s.ticker);
  if (tickers.length === 0) return '—';
  if (tickers.length === 1) return tickers[0];
  if (tickers.length <= 3) return tickers.join(', ');
  return `${tickers[0]} +${tickers.length - 1}`;
}

function BotRow({
  bot,
  strategyName,
}: {
  bot: BotSession;
  /** The strategy's display name (falls back to its key while the catalog loads). */
  strategyName: string;
}) {
  const isArchived = bot.archived_at !== null;
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3 font-semibold">
        <Link
          to={`/bots/${bot.id}`}
          className="text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
        >
          {bot.display_name}
        </Link>
        {isArchived && (
          <span className="ml-2 inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
            Archived
          </span>
        )}
        <span className="mt-0.5 block text-xs font-normal text-slate-500">
          {strategyName}
        </span>
        {bot.orchestrator_id !== null && (
          <Link
            to={`/orchestrators/${bot.orchestrator_id}`}
            className="mt-1 inline-flex items-center gap-1 rounded bg-teal-50 px-1.5 py-0.5 text-xs font-medium text-teal-800 hover:underline"
          >
            Orchestrator · {bot.orchestrator_label ?? 'unknown'}
          </Link>
        )}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={bot.status} />
      </td>
      <td
        className="px-4 py-3 text-slate-700"
        title={new Date(bot.created_at).toLocaleString()}
      >
        {formatAge(bot.created_at)}
      </td>
      <td className="px-4 py-3 font-semibold text-slate-700">
        {bot.symbols.length === 1 ? (
          <Link
            to={`/assets/${bot.symbols[0].ticker}`}
            className="text-emerald-700 hover:underline"
          >
            {bot.symbols[0].ticker}
          </Link>
        ) : (
          <span title={bot.symbols.map((s) => s.ticker).join(', ')}>
            {symbolsSummary(bot)}
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {formatCurrency(bot.current_value)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {bot.eod_value === null ? '—' : formatCurrency(bot.eod_value)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {bot.total_trades}
      </td>
      <td
        className={`px-4 py-3 text-right tabular-nums font-medium ${signClass(bot.realised_pnl)}`}
      >
        {formatCurrency(bot.realised_pnl)}
      </td>
      <td className="px-4 py-3 text-slate-500">
        {bot.last_tick_at ? new Date(bot.last_tick_at).toLocaleString() : '—'}
      </td>
    </tr>
  );
}

export function BotsPage() {
  const [showArchived, setShowArchived] = useState(false);
  const [buildOpen, setBuildOpen] = useState(false);
  const { data, isPending, isError } = useBotSessions(showArchived);
  const { data: strategies } = useStrategies();
  const strategyNames = useMemo(
    () =>
      new Map(
        (Array.isArray(strategies) ? strategies : []).map((s) => [s.key, s.display_name]),
      ),
    [strategies],
  );

  // Stable order everywhere: oldest-created first, so a new bot appends at the end.
  const bots = useMemo(
    () =>
      [...(data?.items ?? [])].sort(
        (a, b) =>
          a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id),
      ),
    [data],
  );
  const total = data?.total ?? 0;

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Bots</h1>
        <div className="flex items-center gap-3">
          <Link
            to="/bots/strategies"
            className="rounded border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
          >
            Strategy guide
          </Link>
          <button
            type="button"
            onClick={() => setBuildOpen(true)}
            className="rounded bg-emerald-500 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
          >
            Build a bot
          </button>
        </div>
      </div>

      <Modal open={buildOpen} onClose={() => setBuildOpen(false)} title="Build a bot">
        <BuildBotCard />
      </Modal>

      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-3 border-b border-slate-200 p-4">
          <h2 className="text-lg font-semibold text-slate-900">Bots</h2>
          {!isPending && !isError && total > 0 && (
            <span className="text-sm text-slate-500">{total} total</span>
          )}
          <label className="ml-auto flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(event) => setShowArchived(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Show archived
          </label>
        </div>

        {isPending && (
          <p role="status" aria-live="polite" className="p-6 text-slate-500">
            Loading bots…
          </p>
        )}

        {isError && (
          <div
            role="alert"
            className="m-4 rounded border border-red-300 bg-red-50 p-4 text-red-800"
          >
            <p className="font-semibold">Could not load bots</p>
            <p className="mt-1 text-sm">Please try again later.</p>
          </div>
        )}

        {!isPending && !isError && bots.length === 0 && (
          <p className="p-6 text-slate-500">
            No bots yet. Use “Build a bot” to get started.
          </p>
        )}

        {!isPending && !isError && bots.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Bot</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Age</th>
                  <th className="px-4 py-3">Symbols</th>
                  <th className="px-4 py-3 text-right">Live value</th>
                  <th className="px-4 py-3 text-right">End of day</th>
                  <th className="px-4 py-3 text-right">Trades</th>
                  <th className="px-4 py-3 text-right">Realised P&amp;L</th>
                  <th className="px-4 py-3">Last Tick</th>
                </tr>
              </thead>
              <tbody>
                {bots.map((bot) => (
                  <BotRow
                    key={bot.id}
                    bot={bot}
                    strategyName={strategyNames.get(bot.strategy_key) ?? bot.strategy_key}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export default BotsPage;
