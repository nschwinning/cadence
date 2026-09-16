import { Link, useParams } from 'react-router-dom';
import { useAIRunDetail } from '../../api/aiPortfolio';
import { formatQuantity } from '../../lib/format';
import type {
  AIPortfolioEvent,
  AIResearchEntry,
  ClosedPosition,
  PaperTrade,
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
      to="/runs"
      className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700 hover:text-emerald-800 hover:underline"
    >
      <span aria-hidden="true">←</span> Back to runs
    </Link>
  );
}

/** A titled card wrapper matching the panels used elsewhere. */
function Card({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-baseline gap-3 border-b border-slate-200 p-4">
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        {typeof count === 'number' && count > 0 && (
          <span className="text-sm text-slate-500">{count} total</span>
        )}
      </div>
      {children}
    </div>
  );
}

/** Safely read a string field off an unknown record. */
function str(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  return typeof value === 'string' && value.trim() ? value : null;
}

/** One AI allocation pick, common to build (`stocks`) and rebalance (`target_allocations`). */
interface AllocationPick {
  ticker: string;
  company_name?: string;
  allocation_pct: number;
  investment_thesis?: string;
  confidence?: number;
}

/** Coerce an unknown array of picks into typed allocation rows, dropping malformed ones. */
function readPicks(value: unknown): AllocationPick[] {
  if (!Array.isArray(value)) return [];
  const picks: AllocationPick[] = [];
  for (const raw of value) {
    if (raw && typeof raw === 'object') {
      const r = raw as Record<string, unknown>;
      if (typeof r.ticker === 'string') {
        picks.push({
          ticker: r.ticker,
          company_name:
            typeof r.company_name === 'string' ? r.company_name : undefined,
          allocation_pct:
            typeof r.allocation_pct === 'number' ? r.allocation_pct : 0,
          investment_thesis:
            typeof r.investment_thesis === 'string'
              ? r.investment_thesis
              : undefined,
          confidence:
            typeof r.confidence === 'number' ? r.confidence : undefined,
        });
      }
    }
  }
  return picks;
}

function PicksTable({ picks }: { picks: AllocationPick[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3">Ticker</th>
            <th className="px-4 py-3">Company</th>
            <th className="px-4 py-3 text-right">Weight</th>
            <th className="px-4 py-3 text-right">Confidence</th>
            <th className="px-4 py-3">Thesis</th>
          </tr>
        </thead>
        <tbody>
          {picks.map((p) => (
            <tr
              key={p.ticker}
              className="border-b border-slate-100 align-top hover:bg-slate-50"
            >
              <td className="px-4 py-3 font-semibold">
                <Link
                  to={`/assets/${p.ticker}`}
                  className="text-emerald-700 hover:underline"
                >
                  {p.ticker}
                </Link>
              </td>
              <td className="px-4 py-3 text-slate-700">
                {p.company_name ?? '—'}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {(p.allocation_pct * 100).toFixed(1)}%
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-500">
                {p.confidence === undefined
                  ? '—'
                  : `${(p.confidence * 100).toFixed(0)}%`}
              </td>
              <td className="px-4 py-3 text-slate-600">
                {p.investment_thesis ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Render the run's reasoning from its `result_payload`. Handles the build shape
 * (`portfolio_name`/`overall_thesis`/`risk_assessment`/`stocks`) and the
 * rebalance shape (`evaluation_summary`/`portfolio_health`/`target_allocations`),
 * falling back to raw JSON for anything unrecognized.
 */
function Reasoning({ event }: { event: AIPortfolioEvent }) {
  const payload = event.result_payload;
  if (!payload) {
    return (
      <Card title="Reasoning">
        <p className="p-6 text-slate-500">
          No reasoning recorded for this run.
        </p>
      </Card>
    );
  }

  const summary =
    str(payload, 'overall_thesis') ?? str(payload, 'evaluation_summary');
  const secondaryLabel = payload.risk_assessment
    ? 'Risk assessment'
    : 'Portfolio health';
  const secondary =
    str(payload, 'risk_assessment') ?? str(payload, 'portfolio_health');
  const name = str(payload, 'portfolio_name');
  const picks = readPicks(payload.stocks ?? payload.target_allocations);
  const recognized = summary || secondary || name || picks.length > 0;

  return (
    <Card title="Reasoning">
      <div className="flex flex-col gap-4 p-4">
        {name && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Portfolio
            </h3>
            <p className="mt-1 text-sm font-medium text-slate-900">{name}</p>
          </div>
        )}
        {summary && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Thesis
            </h3>
            <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
              {summary}
            </p>
          </div>
        )}
        {secondary && (
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {secondaryLabel}
            </h3>
            <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
              {secondary}
            </p>
          </div>
        )}
        {picks.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Allocations
            </h3>
            <PicksTable picks={picks} />
          </div>
        )}
        {!recognized && (
          <pre className="overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-700">
            {JSON.stringify(payload, null, 2)}
          </pre>
        )}
      </div>
    </Card>
  );
}

function ResearchCard({ research }: { research: AIResearchEntry[] | null }) {
  const entries = research ?? [];
  return (
    <Card title="Research" count={entries.length}>
      {entries.length === 0 ? (
        <p className="p-6 text-slate-500">No web searches recorded.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-3 p-4">
          {entries.map((entry, i) => (
            <li
              key={`${entry.query}-${i}`}
              className="rounded border border-slate-200 p-3"
            >
              <div className="flex items-baseline justify-between gap-3">
                <p className="font-medium text-slate-900">{entry.query}</p>
                {entry.error && (
                  <span className="shrink-0 text-xs font-medium text-red-700">
                    {entry.error}
                  </span>
                )}
              </div>
              {entry.results && (
                <pre className="mt-2 max-h-64 overflow-auto rounded bg-slate-50 p-3 text-xs text-slate-700">
                  {JSON.stringify(entry.results, null, 2)}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** A planned order that did not execute, read from the event's `actions_taken`. */
interface SkippedAction {
  ticker: string;
  side: string | null;
  price: number | null;
  reason: string | null;
}

/**
 * Extract the non-executed orders from an event's `actions_taken` payload. Each
 * entry is a serialized `TradeResult`; only the executed ones become
 * `paper_trades` rows, so the skipped ones (with their `reason`) live only here.
 */
function readSkipped(actions: Record<string, unknown>[] | null): SkippedAction[] {
  if (!Array.isArray(actions)) return [];
  const skipped: SkippedAction[] = [];
  for (const raw of actions) {
    if (!raw || typeof raw !== 'object') continue;
    const r = raw as Record<string, unknown>;
    if (r.executed === false && typeof r.ticker === 'string') {
      skipped.push({
        ticker: r.ticker,
        side: typeof r.side === 'string' ? r.side : null,
        price: typeof r.price === 'number' ? r.price : null,
        reason: typeof r.reason === 'string' ? r.reason : null,
      });
    }
  }
  return skipped;
}

function SkippedTradesCard({ skipped }: { skipped: SkippedAction[] }) {
  return (
    <Card title="Skipped / not executed" count={skipped.length}>
      {skipped.length === 0 ? (
        <p className="p-6 text-slate-500">
          Every planned order executed for this run.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Ticker</th>
                <th className="px-4 py-3">Side</th>
                <th className="px-4 py-3 text-right">Price</th>
                <th className="px-4 py-3">Reason</th>
              </tr>
            </thead>
            <tbody>
              {skipped.map((s, i) => (
                <tr
                  key={`${s.ticker}-${i}`}
                  className="border-b border-slate-100 align-top hover:bg-slate-50"
                >
                  <td className="px-4 py-3 font-semibold">
                    <Link
                      to={`/assets/${s.ticker}`}
                      className="text-emerald-700 hover:underline"
                    >
                      {s.ticker}
                    </Link>
                  </td>
                  <td className="px-4 py-3 capitalize text-slate-700">
                    {s.side ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                    {s.price === null ? '—' : eur.format(s.price)}
                  </td>
                  <td className="px-4 py-3 text-amber-700">{s.reason ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function TradesCard({ trades }: { trades: PaperTrade[] }) {
  return (
    <Card title="Opening trades" count={trades.length}>
      {trades.length === 0 ? (
        <p className="p-6 text-slate-500">This run opened no trades.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Ticker</th>
                <th className="px-4 py-3">Side</th>
                <th className="px-4 py-3 text-right">Qty</th>
                <th className="px-4 py-3 text-right">Price</th>
                <th className="px-4 py-3 text-right">Notional</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Executed</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr
                  key={t.id}
                  className="border-b border-slate-100 hover:bg-slate-50"
                >
                  <td className="px-4 py-3 font-semibold">
                    <Link
                      to={`/assets/${t.ticker}`}
                      className="text-emerald-700 hover:underline"
                    >
                      {t.ticker}
                    </Link>
                  </td>
                  <td className="px-4 py-3 capitalize text-slate-700">
                    {t.side}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                    {formatQuantity(t.quantity)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                    {eur.format(t.price)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                    {eur.format(t.notional)}
                  </td>
                  <td className="px-4 py-3 text-slate-700">{t.order_status}</td>
                  <td className="px-4 py-3 text-slate-500">
                    {ts(t.executed_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function ClosedPositionsCard({ positions }: { positions: ClosedPosition[] }) {
  return (
    <Card title="Closed positions" count={positions.length}>
      {positions.length === 0 ? (
        <p className="p-6 text-slate-500">This run closed no positions.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Ticker</th>
                <th className="px-4 py-3 text-right">Qty</th>
                <th className="px-4 py-3 text-right">Entry</th>
                <th className="px-4 py-3 text-right">Exit</th>
                <th className="px-4 py-3 text-right">Realized P&amp;L</th>
                <th className="px-4 py-3 text-right">Return</th>
                <th className="px-4 py-3">Exited</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr
                  key={p.id}
                  className="border-b border-slate-100 hover:bg-slate-50"
                >
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
                  <td className="px-4 py-3 text-slate-500">{ts(p.exit_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function RunHeader({ event }: { event: AIPortfolioEvent }) {
  return (
    <header className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold capitalize tracking-tight text-slate-900">
          {event.event_type} run
        </h1>
        <EventStatusBadge status={event.status} />
      </div>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Created
          </dt>
          <dd className="text-sm text-slate-900">{ts(event.created_at)}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Duration
          </dt>
          <dd className="text-sm text-slate-900">
            {event.duration_ms === null ? '—' : `${event.duration_ms} ms`}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Session
          </dt>
          <dd className="text-sm text-slate-900">
            {event.session_id ? (
              <Link
                to={`/paper-trading/${event.session_id}`}
                className="text-emerald-700 hover:underline"
              >
                View session
              </Link>
            ) : (
              '—'
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Error
          </dt>
          <dd className={`text-sm ${event.error ? 'text-red-700' : 'text-slate-900'}`}>
            {event.error ?? '—'}
          </dd>
        </div>
      </dl>
    </header>
  );
}

export function RunDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const { data, isPending, isError } = useAIRunDetail(id);

  return (
    <section className="flex flex-col gap-6">
      <BackLink />

      {isPending && (
        <p role="status" aria-live="polite" className="text-slate-500">
          Loading run…
        </p>
      )}

      {isError && (
        <div
          role="alert"
          className="rounded border border-red-300 bg-red-50 p-4 text-red-800"
        >
          <p className="font-semibold">Could not load run</p>
          <p className="mt-1 text-sm">
            It may not exist. Return to the{' '}
            <Link to="/runs" className="underline">
              runs list
            </Link>
            .
          </p>
        </div>
      )}

      {!isPending && !isError && data && (
        <>
          <RunHeader event={data.event} />
          <Reasoning event={data.event} />
          <ResearchCard research={data.event.research} />
          <TradesCard trades={data.trades} />
          <SkippedTradesCard skipped={readSkipped(data.event.actions_taken)} />
          <ClosedPositionsCard positions={data.closed_positions} />
        </>
      )}
    </section>
  );
}

export default RunDetailPage;
