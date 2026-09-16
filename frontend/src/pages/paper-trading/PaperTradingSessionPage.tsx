import { Link, useParams } from 'react-router-dom';
import {
  useSessions,
  useSessionTrades,
  useSessionRuns,
  useSessionPositions,
} from '../../api/paperTrading';
import { useSessionEvents } from '../../api/aiPortfolio';
import {
  useRebalanceAction,
  RebalanceButton,
  RebalanceFeedback,
} from './SessionRebalanceCard';
import {
  useCloseAction,
  CloseButton,
  CloseFeedback,
} from './SessionCloseCard';
import { SessionValueChart } from './SessionValueChart';
import { formatQuantity } from '../../lib/format';
import type {
  AIPortfolioEvent,
  ClosedPosition,
  PaperTrade,
  PaperTradingSession,
  SessionRun,
} from '../../types/api';

/** Format a EUR value. */
const eur = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 2,
});

/** Format an ISO timestamp for display, or an em dash when absent. */
function ts(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : '—';
}

/** Colour a P&L value green/red/neutral. */
function pnlClass(value: number): string {
  if (value > 0) return 'text-emerald-700';
  if (value < 0) return 'text-red-700';
  return 'text-slate-700';
}

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-800',
  paused: 'bg-amber-100 text-amber-800',
  stopped: 'bg-slate-100 text-slate-700',
};

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

const EVENT_STATUS_STYLES: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-700',
  running: 'bg-sky-100 text-sky-800',
  succeeded: 'bg-emerald-100 text-emerald-800',
  partial: 'bg-amber-100 text-amber-800',
  skipped: 'bg-slate-100 text-slate-600',
  failed: 'bg-red-100 text-red-800',
};

function EventStatusBadge({ status }: { status: string }) {
  const className = EVENT_STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-700';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${className}`}
    >
      {status}
    </span>
  );
}

function BackLink() {
  return (
    <Link
      to="/paper-trading"
      className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700 hover:text-emerald-800 hover:underline"
    >
      <span aria-hidden="true">←</span> Back to paper trading
    </Link>
  );
}

/** Generic panel wrapper with a header and consistent loading/empty/error states. */
export function Panel({
  title,
  count,
  isPending,
  isError,
  isEmpty,
  emptyText,
  children,
}: {
  title: string;
  count?: number;
  isPending: boolean;
  isError: boolean;
  isEmpty: boolean;
  emptyText: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-baseline gap-3 border-b border-slate-200 p-4">
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        {!isPending && !isError && typeof count === 'number' && count > 0 && (
          <span className="text-sm text-slate-500">{count} total</span>
        )}
      </div>
      {isPending && (
        <p role="status" aria-live="polite" className="p-6 text-slate-500">
          Loading…
        </p>
      )}
      {isError && (
        <div
          role="alert"
          className="m-4 rounded border border-red-300 bg-red-50 p-4 text-sm text-red-800"
        >
          Could not load {title.toLowerCase()}.
        </div>
      )}
      {!isPending && !isError && isEmpty && (
        <p className="p-6 text-slate-500">{emptyText}</p>
      )}
      {!isPending && !isError && !isEmpty && (
        <div className="overflow-x-auto">{children}</div>
      )}
    </div>
  );
}

function TradesPanel({ sessionId }: { sessionId: string }) {
  const { data, isPending, isError } = useSessionTrades(sessionId);
  const trades = data?.items ?? [];
  return (
    <Panel
      title="Trades"
      count={data?.total}
      isPending={isPending}
      isError={isError}
      isEmpty={trades.length === 0}
      emptyText="No trades recorded yet."
    >
      <table className="w-full min-w-[760px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3">Ticker</th>
            <th className="px-4 py-3">Side</th>
            <th className="px-4 py-3 text-right">Qty</th>
            <th className="px-4 py-3 text-right">Price</th>
            <th className="px-4 py-3 text-right">Notional</th>
            <th className="px-4 py-3">Signal</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Executed</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t: PaperTrade) => (
            <tr key={t.id} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="px-4 py-3 font-semibold">
                <Link
                  to={`/assets/${t.ticker}`}
                  className="text-emerald-700 hover:underline"
                >
                  {t.ticker}
                </Link>
              </td>
              <td className="px-4 py-3 capitalize text-slate-700">{t.side}</td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {formatQuantity(t.quantity)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {eur.format(t.price)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {eur.format(t.notional)}
              </td>
              <td className="px-4 py-3 text-slate-700">{t.signal_type}</td>
              <td className="px-4 py-3 text-slate-700">{t.order_status}</td>
              <td className="px-4 py-3 text-slate-500">{ts(t.executed_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function RunsPanel({ sessionId }: { sessionId: string }) {
  const { data, isPending, isError } = useSessionRuns(sessionId);
  const runs = data?.items ?? [];
  return (
    <Panel
      title="Runs"
      count={data?.total}
      isPending={isPending}
      isError={isError}
      isEmpty={runs.length === 0}
      emptyText="No runs recorded yet."
    >
      <table className="w-full min-w-[760px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3">Run At</th>
            <th className="px-4 py-3">Trigger</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3 text-right">Scanned</th>
            <th className="px-4 py-3 text-right">Actionable</th>
            <th className="px-4 py-3 text-right">Executed</th>
            <th className="px-4 py-3 text-right">Skipped</th>
            <th className="px-4 py-3 text-right">Duration</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r: SessionRun) => (
            <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="px-4 py-3 text-slate-500">{ts(r.run_at)}</td>
              <td className="px-4 py-3 text-slate-700">{r.run_trigger}</td>
              <td className="px-4 py-3 text-slate-700">{r.status}</td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {r.signals_scanned}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {r.signals_actionable}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {r.orders_executed}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {r.orders_skipped}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-500">
                {r.duration_ms === null ? '—' : `${r.duration_ms} ms`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function PositionsPanel({ sessionId }: { sessionId: string }) {
  const { data, isPending, isError } = useSessionPositions(sessionId);
  const positions = data?.items ?? [];
  return (
    <Panel
      title="Closed positions"
      count={data?.total}
      isPending={isPending}
      isError={isError}
      isEmpty={positions.length === 0}
      emptyText="No closed positions yet."
    >
      <table className="w-full min-w-[760px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3">Ticker</th>
            <th className="px-4 py-3 text-right">Qty</th>
            <th className="px-4 py-3 text-right">Entry</th>
            <th className="px-4 py-3 text-right">Exit</th>
            <th className="px-4 py-3 text-right">Realized P&amp;L</th>
            <th className="px-4 py-3 text-right">Return</th>
            <th className="px-4 py-3 text-right">Held</th>
            <th className="px-4 py-3">Exited</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p: ClosedPosition) => (
            <tr key={p.id} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="px-4 py-3 font-semibold">
                <Link
                  to={`/assets/${p.ticker}`}
                  className="text-emerald-700 hover:underline"
                >
                  {p.ticker}
                </Link>
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {formatQuantity(p.quantity)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {eur.format(p.entry_price)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {eur.format(p.exit_price)}
              </td>
              <td
                className={`px-4 py-3 text-right tabular-nums font-medium ${pnlClass(p.realized_pnl)}`}
              >
                {eur.format(p.realized_pnl)}
              </td>
              <td
                className={`px-4 py-3 text-right tabular-nums font-medium ${pnlClass(p.return_pct)}`}
              >
                {(p.return_pct * 100).toFixed(2)}%
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-500">
                {p.holding_days}d
              </td>
              <td className="px-4 py-3 text-slate-500">{ts(p.exit_date)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function EventsPanel({ sessionId }: { sessionId: string }) {
  const { data, isPending, isError } = useSessionEvents(sessionId);
  const events = data ?? [];
  return (
    <Panel
      title="AI events"
      count={events.length}
      isPending={isPending}
      isError={isError}
      isEmpty={events.length === 0}
      emptyText="No AI events yet."
    >
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3 text-right">Actions</th>
            <th className="px-4 py-3 text-right">Duration</th>
            <th className="px-4 py-3">Created</th>
            <th className="px-4 py-3">Error</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e: AIPortfolioEvent) => (
            <tr key={e.id} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="px-4 py-3 capitalize text-slate-700">
                {e.event_type}
              </td>
              <td className="px-4 py-3">
                <EventStatusBadge status={e.status} />
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {e.actions_taken?.length ?? 0}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-500">
                {e.duration_ms === null ? '—' : `${e.duration_ms} ms`}
              </td>
              <td className="px-4 py-3 text-slate-500">{ts(e.created_at)}</td>
              <td className="px-4 py-3 max-w-xs truncate text-red-700" title={e.error ?? undefined}>
                {e.error ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function SessionHeader({
  session,
  sessionId,
}: {
  session: PaperTradingSession | undefined;
  sessionId: string;
}) {
  // Action state lives here so the buttons can sit in the header's upper-right
  // corner while their feedback (rebalance progress/result, close confirm
  // dialog/summary) flows full-width below the facts.
  const rebalance = useRebalanceAction(sessionId);
  const close = useCloseAction(sessionId, session?.status);

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      <RebalanceButton action={rebalance} />
      <CloseButton action={close} />
    </div>
  );
  const feedback =
    rebalance.hasFeedback || close.hasFeedback ? (
      <div className="mt-4 flex flex-col gap-3">
        <RebalanceFeedback action={rebalance} />
        <CloseFeedback action={close} />
      </div>
    ) : null;

  if (!session) {
    return (
      <header className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Session
          </h1>
          {actions}
        </div>
        {feedback}
      </header>
    );
  }
  return (
    <header className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {session.strategy_key}
          </h1>
          <StatusBadge status={session.status} />
        </div>
        {actions}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Capital
          </dt>
          <dd className="text-sm text-slate-900">
            {eur.format(session.allocated_capital)}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Schedule
          </dt>
          <dd className="text-sm text-slate-900">{session.schedule_mode}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Total P&amp;L
          </dt>
          <dd className={`text-sm font-medium ${pnlClass(session.total_pnl)}`}>
            {eur.format(session.total_pnl)}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Last run
          </dt>
          <dd className="text-sm text-slate-900">{ts(session.last_run_at)}</dd>
        </div>
      </dl>
      {feedback}
    </header>
  );
}

export function PaperTradingSessionPage() {
  const { id = '' } = useParams<{ id: string }>();
  // The list endpoint is the source of session summary data; find this session.
  const { data: sessionsData } = useSessions();
  const session = sessionsData?.items.find((s) => s.id === id);

  return (
    <section className="flex flex-col gap-6">
      <BackLink />
      <SessionHeader session={session} sessionId={id} />
      <SessionValueChart sessionId={id} />
      <EventsPanel sessionId={id} />
      <TradesPanel sessionId={id} />
      <PositionsPanel sessionId={id} />
      <RunsPanel sessionId={id} />
    </section>
  );
}

export default PaperTradingSessionPage;
