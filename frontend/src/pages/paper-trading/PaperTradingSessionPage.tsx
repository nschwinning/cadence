import { useState, type ComponentProps } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  DEFAULT_SESSIONS_PARAMS,
  useSessions,
  useSessionTrades,
  useSessionRuns,
  useSessionPositions,
  useSessionOrderSync,
  useSessionKpis,
  useSessionSectorPerformance,
  useBenchmarks,
  useChangeSessionBenchmark,
  useChangeSessionScope,
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
import {
  useArchiveAction,
  ArchiveButton,
  ArchiveFeedback,
} from './SessionArchiveCard';
import { SessionValueChart } from './SessionValueChart';
import { SessionSectorPerformanceCard } from './SessionSectorPerformanceCard';
import { Pagination } from '../../components/Pagination';
import { StatTile } from '../../components/dashboard/StatTile';
import { formatCurrency, formatPercent, formatQuantity } from '../../lib/format';
import type {
  AIPortfolioEvent,
  ClosedPosition,
  PaperTrade,
  PaperTradingSession,
  SessionRun,
  SessionSectorPerformance,
} from '../../types/api';

/** The supported asset scopes with their human-readable labels. */
const SCOPE_OPTIONS: { value: 'stocks' | 'crypto' | 'both'; label: string }[] = [
  { value: 'stocks', label: 'Stocks only' },
  { value: 'crypto', label: 'Crypto only' },
  { value: 'both', label: 'Stocks & crypto' },
];

const SCOPE_LABELS: Record<string, string> = Object.fromEntries(
  SCOPE_OPTIONS.map((o) => [o.value, o.label]),
);

/** The two asset classes a position can belong to, mirroring the backend split. */
type HeldAssetClass = 'equity' | 'crypto';

/** The asset classes a scope permits to be held. */
function scopeAllows(scope: string): HeldAssetClass[] {
  if (scope === 'stocks') return ['equity'];
  if (scope === 'crypto') return ['crypto'];
  return ['equity', 'crypto'];
}

/**
 * Derive which asset classes the session currently holds from its by-category
 * performance (a category is held when its market value is positive). Mirrors the
 * backend split: the `crypto` category is the crypto class, everything else is
 * equity. Returns `null` when the attribution has not loaded yet, so callers can
 * fall back to warning on any narrowing.
 */
function heldAssetClasses(
  perf: SessionSectorPerformance | undefined,
): HeldAssetClass[] | null {
  if (!perf) return null;
  const held = new Set<HeldAssetClass>();
  for (const group of perf.by_category) {
    if (group.market_value > 0) {
      held.add(group.key === 'crypto' ? 'crypto' : 'equity');
    }
  }
  return [...held];
}

/**
 * The `signal_type` / `run_trigger` value the backend records for a stop-out.
 * Kept in sync with the backend `STOP_LOSS_SIGNAL_TYPE` / `STOP_LOSS_RUN_TRIGGER`
 * constants so stop-loss activity can be badged in the trades and runs tables.
 */
const STOP_LOSS_MARKER = 'stop_loss';

// Fixed page sizes for the session-detail tables (not user-adjustable): AI events
// and runs are lower-volume, so they page 5 at a time; trades and closed positions
// page 10. Page 1 shows the most-recent rows (the reads are newest-first).
const EVENTS_PAGE_SIZE = 5;
const RUNS_PAGE_SIZE = 5;
const TRADES_PAGE_SIZE = 10;
const POSITIONS_PAGE_SIZE = 10;

/** Format an ISO timestamp for display, or an em dash when absent. */
function ts(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : '—';
}

/** Format a fraction (0.25) as a whole-number percentage ("25%"), or an em dash. */
function pct(value: number | null | undefined): string {
  return value == null ? '—' : `${(value * 100).toFixed(0)}%`;
}

/**
 * Render a value that may be a stop-loss marker. Stop-loss activity gets a
 * distinct amber "Stop-loss" badge; anything else renders as plain text.
 */
function SignalCell({ value }: { value: string }) {
  if (value === STOP_LOSS_MARKER) {
    return (
      <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800">
        Stop-loss
      </span>
    );
  }
  return <>{value}</>;
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
  footer,
}: {
  title: string;
  count?: number;
  isPending: boolean;
  isError: boolean;
  isEmpty: boolean;
  emptyText: string;
  children: React.ReactNode;
  /** Optional card footer (e.g. pagination) shown below loaded content only. */
  footer?: React.ReactNode;
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
        <>
          <div className="overflow-x-auto">{children}</div>
          {footer}
        </>
      )}
    </div>
  );
}

function TradesPanel({ sessionId }: { sessionId: string }) {
  const [page, setPage] = useState(0);
  const { data, isPending, isError } = useSessionTrades(sessionId, {
    limit: TRADES_PAGE_SIZE,
    offset: page * TRADES_PAGE_SIZE,
  });
  const trades = data?.items ?? [];
  const total = data?.total ?? 0;
  return (
    <Panel
      title="Trades"
      count={data?.total}
      isPending={isPending}
      isError={isError}
      isEmpty={total === 0}
      emptyText="No trades recorded yet."
      footer={
        <Pagination
          page={page}
          pageSize={TRADES_PAGE_SIZE}
          total={total}
          onPageChange={setPage}
          label="trades"
        />
      }
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
                {formatCurrency(t.price)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {formatCurrency(t.notional)}
              </td>
              <td className="px-4 py-3 text-slate-700">
                <SignalCell value={t.signal_type} />
              </td>
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
  const [page, setPage] = useState(0);
  const { data, isPending, isError } = useSessionRuns(sessionId, {
    limit: RUNS_PAGE_SIZE,
    offset: page * RUNS_PAGE_SIZE,
  });
  const runs = data?.items ?? [];
  const total = data?.total ?? 0;
  return (
    <Panel
      title="Runs"
      count={data?.total}
      isPending={isPending}
      isError={isError}
      isEmpty={total === 0}
      emptyText="No runs recorded yet."
      footer={
        <Pagination
          page={page}
          pageSize={RUNS_PAGE_SIZE}
          total={total}
          onPageChange={setPage}
          label="runs"
        />
      }
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
              <td className="px-4 py-3">
                {r.ai_portfolio_event_id ? (
                  <Link
                    to={`/runs/${r.ai_portfolio_event_id}`}
                    className="text-emerald-700 hover:text-emerald-800 hover:underline focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  >
                    {ts(r.run_at)}
                  </Link>
                ) : (
                  <span className="text-slate-500">{ts(r.run_at)}</span>
                )}
              </td>
              <td className="px-4 py-3 text-slate-700">
                <SignalCell value={r.run_trigger} />
              </td>
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
  const [page, setPage] = useState(0);
  const { data, isPending, isError } = useSessionPositions(sessionId, {
    limit: POSITIONS_PAGE_SIZE,
    offset: page * POSITIONS_PAGE_SIZE,
  });
  const positions = data?.items ?? [];
  const total = data?.total ?? 0;
  return (
    <Panel
      title="Closed positions"
      count={data?.total}
      isPending={isPending}
      isError={isError}
      isEmpty={total === 0}
      emptyText="No closed positions yet."
      footer={
        <Pagination
          page={page}
          pageSize={POSITIONS_PAGE_SIZE}
          total={total}
          onPageChange={setPage}
          label="closed positions"
        />
      }
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
                {formatCurrency(p.entry_price)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {formatCurrency(p.exit_price)}
              </td>
              <td
                className={`px-4 py-3 text-right tabular-nums font-medium ${pnlClass(p.realized_pnl)}`}
              >
                {formatCurrency(p.realized_pnl)}
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
  const [page, setPage] = useState(0);
  const { data, isPending, isError } = useSessionEvents(sessionId, {
    limit: EVENTS_PAGE_SIZE,
    offset: page * EVENTS_PAGE_SIZE,
  });
  const events = data?.items ?? [];
  const total = data?.total ?? 0;
  return (
    <Panel
      title="AI events"
      count={total}
      isPending={isPending}
      isError={isError}
      isEmpty={total === 0}
      emptyText="No AI events yet."
      footer={
        <Pagination
          page={page}
          pageSize={EVENTS_PAGE_SIZE}
          total={total}
          onPageChange={setPage}
          label="events"
        />
      }
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
  const archive = useArchiveAction(sessionId, session);

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      <RebalanceButton action={rebalance} />
      <CloseButton action={close} />
      <ArchiveButton action={archive} />
    </div>
  );
  const feedback =
    rebalance.hasFeedback || close.hasFeedback || archive.hasFeedback ? (
      <div className="mt-4 flex flex-col gap-3">
        <RebalanceFeedback action={rebalance} />
        <CloseFeedback action={close} />
        <ArchiveFeedback action={archive} />
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
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {session.portfolio_name || session.strategy_key}
            </h1>
            <p className="text-sm text-slate-500">{session.strategy_key}</p>
          </div>
          <StatusBadge status={session.status} />
          {session.archived_at != null && (
            <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
              Archived
            </span>
          )}
        </div>
        {actions}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Capital
          </dt>
          <dd className="text-sm text-slate-900">
            {formatCurrency(session.allocated_capital)}
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
            {formatCurrency(session.total_pnl)}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Last run
          </dt>
          <dd className="text-sm text-slate-900">{ts(session.last_run_at)}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Prompt version
          </dt>
          <dd className="text-sm text-slate-900">
            v{session.rebalance_prompt_version}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Stop-loss
          </dt>
          <dd className="text-sm text-slate-900">
            {session.stop_loss_enabled && session.stop_loss_pct != null
              ? `${(session.stop_loss_pct * 100).toFixed(0)}% below avg cost`
              : 'Off'}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Risk guardrails
          </dt>
          <dd className="text-sm text-slate-900">
            {session.risk_guardrails_enabled ? (
              <ul className="space-y-0.5">
                <li>Max/asset: {pct(session.max_allocation_pct)}</li>
                <li>Max/class: {pct(session.max_asset_class_pct)}</li>
                <li>
                  Min positions:{' '}
                  {session.min_positions == null ? '—' : session.min_positions}
                </li>
                <li>Max invested: {pct(session.max_invested_pct)}</li>
              </ul>
            ) : (
              'Off'
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Scope
          </dt>
          <dd className="text-sm text-slate-900">
            {SCOPE_LABELS[session.asset_types] ?? session.asset_types}
          </dd>
        </div>
        <div>
          <BenchmarkSwitcher sessionId={sessionId} current={session.benchmark} />
        </div>
        <div>
          <ScopeSwitcher sessionId={sessionId} current={session.asset_types} />
        </div>
      </dl>
      {feedback}
    </header>
  );
}

/** A P&L figure coloured green/red/neutral by sign. */
function PnlValue({ value }: { value: number }) {
  return <span className={pnlClass(value)}>{formatCurrency(value)}</span>;
}

/**
 * Session KPI tiles in two groups: "Performance" (value, cash, realised/unrealised
 * P&L, fees, daily average transaction cost, total return, Sharpe, benchmark and
 * excess return — ten tiles laid out five per row) and "Risk & trade quality"
 * (maximum drawdown, win rate, average win/loss, best/worst trade). Tiles read
 * "Not yet available" until their inputs exist (snapshots for the daily average
 * cost and drawdown; stored prices for the benchmark; closed positions for the
 * trade metrics). All tiles use the compact density.
 */
// Session KPI tiles are always rendered at the compact density.
function KpiTile(props: Omit<ComponentProps<typeof StatTile>, 'size'>) {
  return <StatTile size="compact" {...props} />;
}

function KpiRow({ sessionId }: { sessionId: string }) {
  const { data, isPending, isError } = useSessionKpis(sessionId);
  const { data: benchmarks } = useBenchmarks();

  if (isPending || isError || !data) {
    return (
      <div
        role={isError ? 'alert' : 'status'}
        aria-live="polite"
        className="rounded-lg border border-slate-200 bg-white p-6 text-slate-500 shadow-sm"
      >
        {isError ? 'Could not load performance KPIs.' : 'Loading performance…'}
      </div>
    );
  }

  const sharpe =
    data.sharpe_ratio === null ? 'Not yet available' : data.sharpe_ratio.toFixed(2);

  const catalog = Array.isArray(benchmarks) ? benchmarks : [];
  const benchmarkName =
    catalog.find((b) => b.id === data.benchmark)?.name ?? data.benchmark;

  const benchmarkReturn =
    data.benchmark_return_pct === null ? (
      'Not yet available'
    ) : (
      <span className={pnlClass(data.benchmark_return_pct)}>
        {formatPercent(data.benchmark_return_pct)}
      </span>
    );
  const excessReturn =
    data.excess_return_pct === null ? (
      'Not yet available'
    ) : (
      <span className={pnlClass(data.excess_return_pct)}>
        {formatPercent(data.excess_return_pct)}
      </span>
    );
  const excessHint =
    data.excess_return === null ? (
      `vs ${benchmarkName}`
    ) : (
      <>
        <PnlValue value={data.excess_return} /> vs {benchmarkName}
      </>
    );

  // Max drawdown arrives as a non-negative magnitude; show an explicit minus and
  // red when non-zero so it reads as a decline rather than a gain (neutral at 0).
  const maxDrawdown =
    data.max_drawdown === null ? (
      'Not yet available'
    ) : data.max_drawdown === 0 ? (
      '0.00%'
    ) : (
      <span className="text-red-700">−{formatPercent(data.max_drawdown)}</span>
    );
  const winRate =
    data.win_rate === null ? 'Not yet available' : formatPercent(data.win_rate);
  const dailyAvgCost =
    data.daily_avg_transaction_cost === null
      ? 'Not yet available'
      : formatCurrency(data.daily_avg_transaction_cost);

  return (
    <div className="flex flex-col gap-6">
      <section role="group" aria-labelledby="kpi-performance">
        <h3
          id="kpi-performance"
          className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500"
        >
          Performance
        </h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <KpiTile label="Current value" value={formatCurrency(data.current_value)} />
          <KpiTile
            label="Unallocated cash"
            value={formatCurrency(data.unallocated_cash)}
            hint="Uninvested cash in the session"
          />
          <KpiTile
            label="Realised P&L"
            value={<PnlValue value={data.realised_pnl} />}
          />
          <KpiTile
            label="Unrealised P&L"
            value={<PnlValue value={data.unrealised_pnl} />}
          />
          <KpiTile
            label="Transaction fees"
            value={formatCurrency(data.total_fees)}
            hint="$1 per executed trade"
          />
          <KpiTile
            label="Daily avg. transaction cost"
            value={dailyAvgCost}
            hint={
              data.daily_avg_transaction_cost === null
                ? 'Needs a snapshot day'
                : 'Fees per snapshot day'
            }
          />
          <KpiTile
            label="Total return"
            value={
              <span className={pnlClass(data.total_return_pct)}>
                {formatPercent(data.total_return_pct)}
              </span>
            }
            hint={<PnlValue value={data.total_return} />}
          />
          <KpiTile
            label="Sharpe ratio"
            value={sharpe}
            hint={
              data.sharpe_ratio === null
                ? 'Needs more daily history'
                : 'Annualised, from daily NAV'
            }
          />
          <KpiTile
            label="Benchmark return"
            value={benchmarkReturn}
            hint={`${benchmarkName}, buy & hold`}
          />
          <KpiTile label="Excess return" value={excessReturn} hint={excessHint} />
        </div>
      </section>

      <section role="group" aria-labelledby="kpi-risk">
        <h3
          id="kpi-risk"
          className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500"
        >
          Risk & trade quality
        </h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <KpiTile
            label="Maximum drawdown"
            value={maxDrawdown}
            hint={
              data.max_drawdown === null
                ? 'Needs a value snapshot'
                : 'Peak-to-trough, daily NAV'
            }
          />
          <KpiTile
            label="Win rate"
            value={winRate}
            hint={
              data.win_rate === null ? 'No closed positions yet' : 'of closed positions'
            }
          />
          <KpiTile
            label="Average win"
            value={
              data.average_win === null ? (
                'Not yet available'
              ) : (
                <PnlValue value={data.average_win} />
              )
            }
            hint={
              data.average_win === null
                ? 'No winning positions yet'
                : 'per winning position'
            }
          />
          <KpiTile
            label="Average loss"
            value={
              data.average_loss === null ? (
                'Not yet available'
              ) : (
                <PnlValue value={data.average_loss} />
              )
            }
            hint={
              data.average_loss === null
                ? 'No losing positions yet'
                : 'per losing position'
            }
          />
          <KpiTile
            label="Best trade"
            value={
              data.best_trade === null ? (
                'Not yet available'
              ) : (
                <PnlValue value={data.best_trade} />
              )
            }
            hint={
              data.best_trade === null ? 'No closed positions yet' : 'Largest realised gain'
            }
          />
          <KpiTile
            label="Worst trade"
            value={
              data.worst_trade === null ? (
                'Not yet available'
              ) : (
                <PnlValue value={data.worst_trade} />
              )
            }
            hint={
              data.worst_trade === null
                ? 'No closed positions yet'
                : 'Largest realised loss'
            }
          />
        </div>
      </section>
    </div>
  );
}

/**
 * A dropdown to switch the session's benchmark. Preselects the current benchmark,
 * lists the fixed catalog, shows in-flight/error state, and refreshes the session's
 * benchmark figures on success (the mutation invalidates the session, KPIs, and
 * value-history queries).
 */
function BenchmarkSwitcher({
  sessionId,
  current,
}: {
  sessionId: string;
  current: string;
}) {
  const { data: benchmarks } = useBenchmarks();
  const mutation = useChangeSessionBenchmark(sessionId);
  const catalog = Array.isArray(benchmarks) ? benchmarks : null;
  return (
    <div>
      <label
        htmlFor="benchmark-select"
        className="text-xs font-semibold uppercase tracking-wide text-slate-500"
      >
        Benchmark
      </label>
      <select
        id="benchmark-select"
        className="mt-1 block w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 disabled:opacity-60"
        value={current}
        disabled={mutation.isPending || !catalog}
        onChange={(e) => mutation.mutate(e.target.value)}
      >
        {(catalog ?? [{ id: current, name: current }]).map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
          </option>
        ))}
      </select>
      {mutation.isPending && (
        <p role="status" aria-live="polite" className="mt-1 text-xs text-slate-500">
          Updating…
        </p>
      )}
      {mutation.isError && (
        <p role="alert" className="mt-1 text-xs text-red-700">
          Could not change the benchmark.
        </p>
      )}
    </div>
  );
}

/**
 * A dropdown to change the session's asset scope. Preselects the current scope and
 * shows in-flight/error state. When the selected scope would liquidate currently
 * held positions — a narrowing that excludes a held position's asset class — it
 * shows a confirmation warning and only requests the change after the user
 * confirms; declining leaves the control on the current scope and requests
 * nothing. A non-liquidating change (a widening, or a narrowing that excludes
 * nothing held) requests immediately. Held classes are derived from the session's
 * by-category performance; if that has not loaded, any narrowing warns.
 */
function ScopeSwitcher({
  sessionId,
  current,
}: {
  sessionId: string;
  current: string;
}) {
  const mutation = useChangeSessionScope(sessionId);
  const { data: sectorPerformance } = useSessionSectorPerformance(sessionId);
  const [pending, setPending] = useState<'stocks' | 'crypto' | 'both' | null>(
    null,
  );

  const held = heldAssetClasses(sectorPerformance);

  /** Whether switching to `next` would liquidate a currently-held position. */
  function wouldLiquidate(next: string): boolean {
    const allowed = scopeAllows(next);
    if (held === null) {
      // Attribution not loaded: warn whenever the change drops an allowed class.
      return scopeAllows(current).some((c) => !allowed.includes(c));
    }
    return held.some((c) => !allowed.includes(c));
  }

  function handleSelect(next: 'stocks' | 'crypto' | 'both') {
    if (next === current) return;
    if (wouldLiquidate(next)) {
      setPending(next);
      return;
    }
    mutation.mutate(next);
  }

  return (
    <div>
      <label
        htmlFor="scope-select"
        className="text-xs font-semibold uppercase tracking-wide text-slate-500"
      >
        Change scope
      </label>
      <select
        id="scope-select"
        className="mt-1 block w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 disabled:opacity-60"
        value={current}
        disabled={mutation.isPending}
        onChange={(e) =>
          handleSelect(e.target.value as 'stocks' | 'crypto' | 'both')
        }
      >
        {SCOPE_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {pending && (
        <div
          role="alertdialog"
          aria-label="Confirm scope change"
          className="mt-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900"
        >
          <p>
            Changing to “{SCOPE_LABELS[pending]}” will sell all out-of-scope
            holdings. This cannot be undone.
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              className="rounded bg-amber-600 px-2 py-1 font-medium text-white hover:bg-amber-700"
              onClick={() => {
                mutation.mutate(pending);
                setPending(null);
              }}
            >
              Sell &amp; change
            </button>
            <button
              type="button"
              className="rounded border border-slate-300 bg-white px-2 py-1 font-medium text-slate-700 hover:bg-slate-50"
              onClick={() => setPending(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {mutation.isPending && (
        <p role="status" aria-live="polite" className="mt-1 text-xs text-slate-500">
          Updating…
        </p>
      )}
      {mutation.isError && (
        <p role="alert" className="mt-1 text-xs text-red-700">
          Could not change the scope.
        </p>
      )}
    </div>
  );
}

export function PaperTradingSessionPage() {
  const { id = '' } = useParams<{ id: string }>();
  // The list endpoint is the source of session summary data; find this session.
  // Include archived rows so an archived session can still be viewed/unarchived.
  const { data: sessionsData } = useSessions({
    ...DEFAULT_SESSIONS_PARAMS,
    includeArchived: true,
  });
  const session = sessionsData?.items.find((s) => s.id === id);
  // Reconcile broker order statuses on mount and poll until all fills settle;
  // the hook invalidates the trades/positions/chart queries as statuses change.
  useSessionOrderSync(id);

  return (
    <section className="flex flex-col gap-6">
      <BackLink />
      <SessionHeader session={session} sessionId={id} />
      <KpiRow sessionId={id} />
      <SessionValueChart sessionId={id} />
      <SessionSectorPerformanceCard sessionId={id} />
      <EventsPanel sessionId={id} />
      <TradesPanel sessionId={id} />
      <PositionsPanel sessionId={id} />
      <RunsPanel sessionId={id} />
    </section>
  );
}

export default PaperTradingSessionPage;
