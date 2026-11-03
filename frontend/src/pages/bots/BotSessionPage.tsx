import type { ComponentProps } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  useBotSession,
  useBotKpis,
  useBotTrades,
  useStopBotSession,
  useArchiveBotSession,
} from '../../api/bots';
import { BotValueChart } from './BotValueChart';
import { StatTile } from '../../components/dashboard/StatTile';
import {
  FreshnessBadge,
  Panel,
} from '../paper-trading/PaperTradingSessionPage';
import {
  formatCurrency,
  formatPercent,
  formatQuantity,
} from '../../lib/format';
import type { BotSession, BotTrade } from '../../types/api';

/** Status pill colors per bot status. */
const STATUS_STYLES: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-800',
  stopped: 'bg-slate-100 text-slate-700',
  archived: 'bg-slate-100 text-slate-500',
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

/** A P&L figure coloured green/red/neutral by sign. */
function PnlValue({ value }: { value: number }) {
  return <span className={pnlClass(value)}>{formatCurrency(value)}</span>;
}

/** Compact summary of a bot's traded symbol set. */
function symbolsSummary(bot: BotSession): string {
  const tickers = bot.symbols.map((s) => s.ticker);
  if (tickers.length === 0) return '—';
  if (tickers.length <= 3) return tickers.join(', ');
  return `${tickers[0]} +${tickers.length - 1}`;
}

/** A bot's display label: its explicit label, else strategy + symbol summary. */
function botLabel(bot: BotSession): string {
  return bot.label || `${bot.strategy_key} · ${symbolsSummary(bot)}`;
}

/** Render a strategy-param object as a compact `key: value` list. */
function paramsSummary(params: Record<string, unknown>): string {
  const entries = Object.entries(params);
  if (entries.length === 0) return '—';
  return entries.map(([k, v]) => `${k}: ${String(v)}`).join(', ');
}

function BackLink() {
  return (
    <Link
      to="/bots"
      className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700 hover:text-emerald-800 hover:underline"
    >
      <span aria-hidden="true">←</span> Back to bots
    </Link>
  );
}

// Bot KPI tiles are always rendered at the compact density.
function KpiTile(props: Omit<ComponentProps<typeof StatTile>, 'size'>) {
  return <StatTile size="compact" {...props} />;
}

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

function SessionHeader({ sessionId }: { sessionId: string }) {
  const { data: bot } = useBotSession(sessionId);
  const stop = useStopBotSession();
  const archive = useArchiveBotSession();

  const actions = bot ? (
    <div className="flex flex-wrap items-center gap-2">
      {bot.status === 'active' && (
        <button
          type="button"
          onClick={() => stop.mutate(sessionId)}
          disabled={stop.isPending}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {stop.isPending ? 'Stopping…' : 'Stop'}
        </button>
      )}
      {bot.status === 'stopped' && (
        <button
          type="button"
          onClick={() => archive.mutate(sessionId)}
          disabled={archive.isPending}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {archive.isPending ? 'Archiving…' : 'Archive'}
        </button>
      )}
    </div>
  ) : null;

  const feedback =
    stop.isError || archive.isError ? (
      <p role="alert" className="mt-4 text-sm text-red-700">
        {stop.isError ? 'Could not stop the bot.' : 'Could not archive the bot.'}
      </p>
    ) : null;

  if (!bot) {
    return (
      <header className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Bot</h1>
      </header>
    );
  }

  return (
    <header className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {botLabel(bot)}
            </h1>
            <p className="text-sm text-slate-500">{bot.strategy_key}</p>
          </div>
          <StatusBadge status={bot.status} />
          {bot.archived_at != null && (
            <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
              Archived
            </span>
          )}
        </div>
        {actions}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Fact
          label="Symbols"
          value={
            <span title={bot.symbols.map((s) => s.ticker).join(', ')}>
              {bot.symbols.length} ({symbolsSummary(bot)})
            </span>
          }
        />
        <Fact label="Capital" value={formatCurrency(bot.allocated_capital)} />
        <Fact label="Cash" value={formatCurrency(bot.cash)} />
        <Fact label="Benchmark" value={bot.benchmark} />
        <Fact label="Parameters" value={paramsSummary(bot.strategy_params)} />
        <Fact
          label="Sizing"
          value={
            bot.sizing_method === 'atr_risk'
              ? `ATR risk ${(bot.risk_pct * 100).toFixed(1)}% · k=${bot.atr_k}`
              : 'All-in'
          }
        />
        <Fact
          label="Max per-name"
          value={`${(bot.max_position_pct * 100).toFixed(0)}%`}
        />
        <Fact label="Max positions" value={String(bot.max_positions)} />
        <Fact
          label="Take-profit"
          value={
            bot.take_profit_pct == null
              ? 'Off'
              : `${(bot.take_profit_pct * 100).toFixed(0)}% above entry`
          }
        />
        <Fact
          label="Stop-loss"
          value={
            bot.stop_loss_pct == null
              ? 'Off'
              : `${(bot.stop_loss_pct * 100).toFixed(0)}% below entry`
          }
        />
        <Fact
          label="Drawdown stop"
          value={`${(bot.drawdown_stop_pct * 100).toFixed(0)}% from peak`}
        />
        <Fact
          label="Cash buffer"
          value={`${(bot.cash_buffer_pct * 100).toFixed(0)}%`}
        />
        <Fact label="Open positions" value={String(bot.positions.length)} />
        <Fact label="Last tick" value={ts(bot.last_tick_at)} />
        <Fact label="Created" value={ts(bot.created_at)} />
      </dl>
      {feedback}
    </header>
  );
}

function KpiRow({ sessionId }: { sessionId: string }) {
  const { data, isPending, isError } = useBotKpis(sessionId);

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

  const maxDrawdown =
    data.max_drawdown === 0 ? (
      '0.00%'
    ) : (
      <span className="text-red-700">−{formatPercent(data.max_drawdown)}</span>
    );

  return (
    <section role="group" aria-labelledby="bot-kpi-performance">
      <div className="mb-3 flex items-center gap-2">
        <h3
          id="bot-kpi-performance"
          className="text-sm font-semibold uppercase tracking-wide text-slate-500"
        >
          Performance
        </h3>
        <FreshnessBadge kind="live" />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile label="Current value" value={formatCurrency(data.current_value)} />
        <KpiTile
          label="Allocated capital"
          value={formatCurrency(data.allocated_capital)}
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
          label="Maximum drawdown"
          value={maxDrawdown}
          hint="Peak-to-trough, daily NAV"
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
        />
        <KpiTile label="Total trades" value={String(data.total_trades)} />
      </div>
    </section>
  );
}

function PositionsPanel({ sessionId }: { sessionId: string }) {
  const { data: bot, isPending, isError } = useBotSession(sessionId);
  const positions = bot?.positions ?? [];
  // Stable order: ascending ticker, matching the deterministic tick entry order.
  const sorted = [...positions].sort((a, b) => a.ticker.localeCompare(b.ticker));
  return (
    <Panel
      title="Open positions"
      count={positions.length}
      isPending={isPending}
      isError={isError}
      isEmpty={positions.length === 0}
      emptyText="No open positions — the bot is holding cash."
    >
      <table className="w-full min-w-[520px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3">Ticker</th>
            <th className="px-4 py-3 text-right">Quantity</th>
            <th className="px-4 py-3 text-right">Avg price</th>
            <th className="px-4 py-3 text-right">Cost basis</th>
            <th className="px-4 py-3">Opened</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => (
            <tr
              key={p.asset_id}
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
                {formatCurrency(p.avg_price)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {formatCurrency(p.quantity * p.avg_price)}
              </td>
              <td className="px-4 py-3 text-slate-500">{ts(p.opened_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function TradesPanel({ sessionId }: { sessionId: string }) {
  const { data, isPending, isError } = useBotTrades(sessionId);
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
    >
      <table className="w-full min-w-[720px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <th className="px-4 py-3">Ticker</th>
            <th className="px-4 py-3">Side</th>
            <th className="px-4 py-3 text-right">Qty</th>
            <th className="px-4 py-3 text-right">Price</th>
            <th className="px-4 py-3 text-right">Fees</th>
            <th className="px-4 py-3">Reason</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Executed</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t: BotTrade) => (
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
                {t.filled_price == null ? '—' : formatCurrency(t.filled_price)}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                {formatCurrency(t.fees)}
              </td>
              <td className="px-4 py-3 text-slate-700">{t.reason ?? '—'}</td>
              <td className="px-4 py-3 text-slate-700">{t.status}</td>
              <td className="px-4 py-3 text-slate-500">{ts(t.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

export function BotSessionPage() {
  const { id = '' } = useParams<{ id: string }>();
  return (
    <section className="flex flex-col gap-6">
      <BackLink />
      <SessionHeader sessionId={id} />
      <KpiRow sessionId={id} />
      <PositionsPanel sessionId={id} />
      <BotValueChart sessionId={id} />
      <TradesPanel sessionId={id} />
    </section>
  );
}

export default BotSessionPage;
