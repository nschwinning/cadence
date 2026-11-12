import { useState } from 'react';
import {
  useAdminAccount,
  useFlattenOrphans,
  useReconcileOrders,
  useRestorePositions,
  useWriteOffPositions,
} from '../../api/admin';
import { Modal } from '../../components/Modal';
import { formatCurrency, formatQuantity } from '../../lib/format';
import type {
  AdminAccount,
  AdminCashCheck,
  AdminCashContributorKind,
  AdminFlattenOutcome,
  AdminOpenOrder,
  AdminPosition,
  AdminPositionStatus,
  AdminReconcileResult,
  AdminUnresolvedOrder,
} from '../../types/api';

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white shadow-sm';
const TH_CLASS = 'px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500';
const BUTTON_CLASS =
  'rounded border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60';
const DANGER_BUTTON_CLASS =
  'rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60';

const KIND_LABELS: Record<AdminCashContributorKind, string> = {
  portfolio: 'AI portfolio',
  bot: 'Bot',
  orchestrator: 'Orchestrator (free capital)',
  returning_bot: 'Stopped bot (cash returning)',
};

const STATUS_LABELS: Record<AdminPositionStatus, string> = {
  matched: 'Matched',
  orphan: 'Orphan',
  shortfall: 'Shortfall',
  short: 'Short',
};

const STATUS_STYLES: Record<AdminPositionStatus, string> = {
  matched: 'bg-emerald-50 text-emerald-700',
  orphan: 'bg-amber-100 text-amber-800',
  shortfall: 'bg-red-50 text-red-700',
  short: 'bg-red-50 text-red-700',
};

/** Which correction an action applies: sell orphans, or buy back shortfalls/shorts. */
type AdminAction = 'flatten' | 'restore' | 'writeoff';

const SKIP_REASONS: Record<string, string> = {
  not_orphan: 'no longer an orphan',
  not_short: 'no longer short of Cadence’s quantity',
  not_eligible: 'not a crypto fee difference within 1%',
  below_minimum: 'below the $10 minimum for crypto orders',
  pending_order: 'has an open order',
  market_closed: 'equity market is closed',
  not_found: 'not held in the account',
};

/** A titled card section. */
function Card({
  title,
  actions,
  children,
}: {
  title: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className={CARD_CLASS}>
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 p-4">
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        {actions}
      </div>
      {children}
    </div>
  );
}

function AccountCard({ account }: { account: NonNullable<AdminAccount['account']> }) {
  const figures = [
    { label: 'Cash', value: account.cash },
    { label: 'Cash buying power', value: account.cash_buying_power },
    { label: 'Margin buying power', value: account.buying_power },
    { label: 'Total value', value: account.portfolio_value },
  ];
  return (
    <Card title="Account">
      <dl className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
        {figures.map((f) => (
          <div key={f.label}>
            <dt className="text-sm text-slate-500">{f.label}</dt>
            <dd className="text-xl font-semibold tabular-nums text-slate-900">
              {f.value === null ? '—' : formatCurrency(f.value)}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function CashCheckCard({ check }: { check: AdminCashCheck }) {
  return (
    <Card title="Cash check">
      {check.shortfall && (
        <div
          role="alert"
          className="m-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800"
        >
          Cadence has committed {formatCurrency(-check.difference)} more cash than the account
          holds. Orders may be rejected for insufficient buying power.
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              <th className={TH_CLASS}>Holder</th>
              <th className={TH_CLASS}>Kind</th>
              <th className={`${TH_CLASS} text-right`}>Cash</th>
            </tr>
          </thead>
          <tbody>
            {check.contributors.map((c) => (
              <tr key={`${c.kind}-${c.id}`} className="border-b border-slate-100">
                <td className="px-4 py-2 text-slate-700">{c.label}</td>
                <td className="px-4 py-2 text-slate-500">{KIND_LABELS[c.kind]}</td>
                <td className="px-4 py-2 text-right tabular-nums text-slate-700">
                  {formatCurrency(c.amount)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-slate-50">
            <tr>
              <td colSpan={2} className="px-4 py-2 font-semibold text-slate-900">
                Committed by Cadence
              </td>
              <td className="px-4 py-2 text-right font-semibold tabular-nums text-slate-900">
                {formatCurrency(check.committed_total)}
              </td>
            </tr>
            {check.short_proceeds > 0 && (
              <>
                <tr>
                  <td colSpan={2} className="px-4 py-2 text-slate-500">
                    Reported cash
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-500">
                    {formatCurrency(check.reported_cash)}
                  </td>
                </tr>
                <tr>
                  <td colSpan={2} className="px-4 py-2 text-slate-500">
                    Short-sale proceeds (excluded)
                  </td>
                  <td
                    data-testid="short-proceeds"
                    className="px-4 py-2 text-right tabular-nums text-slate-500"
                  >
                    −{formatCurrency(check.short_proceeds)}
                  </td>
                </tr>
              </>
            )}
            <tr>
              <td colSpan={2} className="px-4 py-2 text-slate-700">
                Account cash
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-slate-700">
                {formatCurrency(check.account_cash)}
              </td>
            </tr>
            <tr>
              <td colSpan={2} className="px-4 py-2 font-semibold text-slate-900">
                Difference
              </td>
              <td
                data-testid="cash-difference"
                className={`px-4 py-2 text-right font-semibold tabular-nums ${
                  check.shortfall ? 'text-red-700' : 'text-emerald-700'
                }`}
              >
                {formatCurrency(check.difference)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}

function OpenOrdersCard({ orders }: { orders: AdminOpenOrder[] }) {
  return (
    <Card title="Open orders">
      {orders.length === 0 ? (
        <p className="p-4 text-sm text-slate-500">No open orders.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className={TH_CLASS}>Symbol</th>
                <th className={TH_CLASS}>Side</th>
                <th className={`${TH_CLASS} text-right`}>Quantity</th>
                <th className={TH_CLASS}>Type</th>
                <th className={TH_CLASS}>Status</th>
                <th className={TH_CLASS}>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o, i) => (
                <tr key={o.order_id ?? `${o.symbol}-${i}`} className="border-b border-slate-100">
                  <td className="px-4 py-2 font-medium text-slate-900">{o.symbol}</td>
                  <td className="px-4 py-2 text-slate-700">{o.side}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-700">
                    {formatQuantity(o.quantity)}
                  </td>
                  <td className="px-4 py-2 text-slate-700">{o.order_type}</td>
                  <td className="px-4 py-2 text-slate-700">{o.status}</td>
                  <td className="px-4 py-2 text-slate-500">
                    {o.submitted_at ? new Date(o.submitted_at).toLocaleString() : '—'}
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

function PositionStatus({ position }: { position: AdminPosition }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span
        className={`rounded px-1.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[position.status]}`}
      >
        {STATUS_LABELS[position.status]}
      </span>
      {position.pending_order && (
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-600">
          Pending order
        </span>
      )}
    </span>
  );
}

function PositionsCard({
  positions,
  onAction,
  busy,
}: {
  positions: AdminPosition[];
  onAction: (action: AdminAction, targets: AdminPosition[], symbol: string | null) => void;
  busy: boolean;
}) {
  const flattenable = positions.filter((p) => p.flattenable);
  const restorable = positions.filter((p) => p.restorable);
  const writable = positions.filter((p) => p.write_off_eligible);
  return (
    <Card
      title="Positions"
      actions={
        (flattenable.length > 0 || restorable.length > 0 || writable.length > 0) && (
          <span className="flex flex-wrap gap-2">
            {writable.length > 0 && (
              <button
                type="button"
                className={BUTTON_CLASS}
                disabled={busy}
                onClick={() => onAction('writeoff', writable, null)}
              >
                Write off all
              </button>
            )}
            {restorable.length > 0 && (
              <button
                type="button"
                className={BUTTON_CLASS}
                disabled={busy}
                onClick={() => onAction('restore', restorable, null)}
              >
                Restore all
              </button>
            )}
            {flattenable.length > 0 && (
              <button
                type="button"
                className={DANGER_BUTTON_CLASS}
                disabled={busy}
                onClick={() => onAction('flatten', flattenable, null)}
              >
                Flatten all orphans
              </button>
            )}
          </span>
        )
      }
    >
      <p className="px-4 pt-3 text-sm text-slate-500">
        Broker holdings compared with every Cadence portfolio and bot. An orphan is the
        quantity no Cadence record claims; only that excess is ever sold. A shortfall or
        short can be restored by buying back exactly what Cadence tracks.
      </p>
      {positions.length === 0 ? (
        <p className="p-4 text-sm text-slate-500">No positions.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className={TH_CLASS}>Symbol</th>
                <th className={`${TH_CLASS} text-right`}>Broker</th>
                <th className={`${TH_CLASS} text-right`}>Cadence</th>
                <th className={`${TH_CLASS} text-right`}>Orphan</th>
                <th className={`${TH_CLASS} text-right`}>Market value</th>
                <th className={TH_CLASS}>Status</th>
                <th className={TH_CLASS}>
                  <span className="sr-only">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.symbol} className="border-b border-slate-100">
                  <td className="px-4 py-2 font-medium text-slate-900">
                    {p.symbol}
                    {p.asset_class === 'crypto' && (
                      <span className="ml-2 text-xs text-slate-400">crypto</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-700">
                    {formatQuantity(p.broker_quantity)}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-700">
                    {formatQuantity(p.cadence_quantity)}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-700">
                    {p.status === 'orphan' ? formatQuantity(p.orphan_quantity) : '—'}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-700">
                    {p.market_value === null ? '—' : formatCurrency(p.market_value)}
                  </td>
                  <td className="px-4 py-2">
                    <PositionStatus position={p} />
                  </td>
                  <td className="px-4 py-2 text-right">
                    {p.flattenable && (
                      <button
                        type="button"
                        className={BUTTON_CLASS}
                        disabled={busy}
                        aria-label={`Flatten ${p.symbol}`}
                        onClick={() => onAction('flatten', [p], p.symbol)}
                      >
                        Flatten
                      </button>
                    )}
                    {p.write_off_eligible && (
                      <button
                        type="button"
                        className={BUTTON_CLASS}
                        disabled={busy}
                        aria-label={`Write off ${p.symbol}`}
                        onClick={() => onAction('writeoff', [p], p.symbol)}
                      >
                        Write off {formatQuantity(p.write_off_quantity)}
                      </button>
                    )}
                    {p.restorable && (
                      <button
                        type="button"
                        className={BUTTON_CLASS}
                        disabled={busy}
                        aria-label={`Restore ${p.symbol}`}
                        onClick={() => onAction('restore', [p], p.symbol)}
                      >
                        Restore {formatQuantity(p.restore_quantity)}
                      </button>
                    )}
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

const CONFIRM_COPY: Record<
  AdminAction,
  { title: string; intro: string; note: string; button: string }
> = {
  flatten: {
    title: 'Sell orphan positions?',
    intro: 'This places market sell orders in the broker account for:',
    note: 'Quantities are recomputed when the order is placed, so the account ends up holding exactly what Cadence’s portfolios and bots track at that moment.',
    button: 'Sell',
  },
  restore: {
    title: 'Buy back to Cadence’s positions?',
    intro: 'This places market buy orders in the broker account for:',
    note: 'Quantities are recomputed when the order is placed, so the account ends up holding exactly what Cadence’s portfolios and bots track at that moment.',
    button: 'Buy',
  },
  writeoff: {
    title: 'Write off crypto fee differences?',
    intro: 'This lowers Cadence’s recorded quantities to what the account holds for:',
    note: 'No order is sent. The difference is the fee the broker took in the coin; it is removed from the AI portfolios holding it, in proportion to their share.',
    button: 'Write off',
  },
};

function actionQuantity(action: AdminAction, t: AdminPosition): number {
  if (action === 'restore') return t.restore_quantity;
  if (action === 'writeoff') return t.write_off_quantity;
  return t.orphan_quantity;
}

function ConfirmAction({
  action,
  targets,
  onCancel,
  onConfirm,
}: {
  action: AdminAction;
  targets: AdminPosition[];
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const copy = CONFIRM_COPY[action];
  return (
    <div className="mx-auto w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
      <h2 className="text-lg font-semibold text-slate-900">{copy.title}</h2>
      <p className="mt-2 text-sm text-slate-600">{copy.intro}</p>
      <ul className="mt-3 flex flex-col gap-1 text-sm">
        {targets.map((t) => (
          <li key={t.symbol} className="flex justify-between gap-4">
            <span className="font-medium text-slate-900">{t.symbol}</span>
            <span className="tabular-nums text-slate-700">
              {formatQuantity(actionQuantity(action, t))}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-slate-500">{copy.note}</p>
      <div className="mt-5 flex justify-end gap-2">
        <button type="button" className={BUTTON_CLASS} onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className={DANGER_BUTTON_CLASS} onClick={onConfirm}>
          {copy.button}
        </button>
      </div>
    </div>
  );
}

function outcomeText(o: AdminFlattenOutcome): string {
  if (o.result === 'sold') return `sold ${formatQuantity(o.quantity ?? 0)}`;
  if (o.result === 'written_off') return `written off ${formatQuantity(o.quantity ?? 0)}`;
  if (o.result === 'bought') {
    const bought = `bought ${formatQuantity(o.quantity ?? 0)}`;
    // A short's cover may still be filling: the note says what is left to buy.
    return o.reason ? `${bought} — ${o.reason}` : bought;
  }
  if (o.result === 'skipped') return `skipped — ${SKIP_REASONS[o.reason ?? ''] ?? o.reason}`;
  return `failed — ${o.reason ?? 'broker rejected the order'}`;
}

function Outcomes({ outcomes }: { outcomes: AdminFlattenOutcome[] }) {
  return (
    <div
      role="status"
      data-testid="flatten-outcomes"
      className="rounded border border-slate-200 bg-slate-50 p-4 text-sm"
    >
      <p className="font-semibold text-slate-900">Result</p>
      {outcomes.length === 0 ? (
        <p className="mt-1 text-slate-600">Nothing to flatten.</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-0.5">
          {outcomes.map((o) => (
            <li
              key={o.symbol}
              className={o.result === 'failed' ? 'text-red-700' : 'text-slate-700'}
            >
              <span className="font-medium">{o.symbol}</span>: {outcomeText(o)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function UnresolvedOrdersCard({
  orders,
  onReconcile,
  busy,
  result,
}: {
  orders: AdminUnresolvedOrder[];
  onReconcile: () => void;
  busy: boolean;
  result: AdminReconcileResult | undefined;
}) {
  return (
    <Card
      title="Unresolved orders"
      actions={
        <button type="button" className={BUTTON_CLASS} disabled={busy} onClick={onReconcile}>
          {busy ? 'Reconciling…' : 'Reconcile now'}
        </button>
      }
    >
      {result && (
        <p role="status" data-testid="reconcile-result" className="px-4 pt-3 text-sm text-slate-700">
          Reconciled: {result.booked} booked, {result.closed} closed, {result.remaining} still
          open.
        </p>
      )}
      {orders.length === 0 ? (
        <p className="p-4 text-sm text-slate-500">
          Every order Cadence sent is recorded.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className={TH_CLASS}>Owner</th>
                <th className={TH_CLASS}>Symbol</th>
                <th className={TH_CLASS}>Side</th>
                <th className={`${TH_CLASS} text-right`}>Quantity</th>
                <th className={TH_CLASS}>Status</th>
                <th className={TH_CLASS}>Sent</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.client_order_id} className="border-b border-slate-100">
                  <td className="px-4 py-2 text-slate-700">{o.owner_label}</td>
                  <td className="px-4 py-2 font-medium text-slate-900">{o.ticker}</td>
                  <td className="px-4 py-2 text-slate-700">{o.side}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-700">
                    {formatQuantity(o.quantity)}
                  </td>
                  <td className="px-4 py-2 text-slate-700">
                    {o.broker_status ?? o.state}
                    {o.error && <span className="ml-2 text-xs text-red-700">{o.error}</span>}
                  </td>
                  <td className="px-4 py-2 text-slate-500">
                    {new Date(o.created_at).toLocaleString()}
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

/**
 * Admin — the shared broker account every portfolio, bot and orchestrator trades in:
 * live balances, the cash Cadence has committed against the account's cash, open
 * orders, and a per-symbol comparison of broker holdings with Cadence's books. Orphan
 * positions (shares no Cadence record claims) can be sold, and shortfalls or shorts
 * bought back to Cadence's quantity, after confirmation; the server recomputes the
 * quantity at execution. Journaled orders not yet booked are listed and can be
 * reconciled on demand.
 */
export function AdminPage() {
  const { data, isPending, isError, refetch, isFetching } = useAdminAccount();
  const flatten = useFlattenOrphans();
  const restore = useRestorePositions();
  const writeOff = useWriteOffPositions();
  const reconcile = useReconcileOrders();
  const [pending, setPending] = useState<{
    action: AdminAction;
    targets: AdminPosition[];
    symbol: string | null;
  } | null>(null);
  // The most recent flatten/restore drives the outcome panel.
  const [lastAction, setLastAction] = useState<AdminAction | null>(null);
  const mutations = { flatten, restore, writeoff: writeOff };
  const lastMutation = lastAction ? mutations[lastAction] : flatten;

  const confirm = () => {
    if (pending === null) return;
    mutations[pending.action].mutate(pending.symbol);
    setLastAction(pending.action);
    setPending(null);
  };

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Admin</h1>
          <p className="mt-1 text-sm text-slate-500">
            The broker account shared by every portfolio, bot and orchestrator.
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
          Loading the broker account…
        </p>
      )}

      {(isError || (data && !data.broker_available)) && (
        <div role="alert" className="rounded border border-red-300 bg-red-50 p-4 text-red-800">
          <p className="font-semibold">Broker unavailable</p>
          <p className="mt-1 text-sm">
            {data?.reason ?? 'The broker account could not be read. Please try again later.'}
          </p>
        </div>
      )}

      {lastAction && lastMutation.isError && (
        <div role="alert" className="rounded border border-red-300 bg-red-50 p-4 text-red-800">
          The request failed. Orders may not have been placed; refresh to check.
        </div>
      )}
      {lastAction && lastMutation.data && <Outcomes outcomes={lastMutation.data.outcomes} />}

      {data?.broker_available && data.account && data.cash_check && (
        <>
          <AccountCard account={data.account} />
          <CashCheckCard check={data.cash_check} />
          <PositionsCard
            positions={data.positions}
            busy={flatten.isPending || restore.isPending || writeOff.isPending}
            onAction={(action, targets, symbol) => setPending({ action, targets, symbol })}
          />
          <UnresolvedOrdersCard
            orders={data.unresolved_orders}
            busy={reconcile.isPending}
            result={reconcile.data}
            onReconcile={() => reconcile.mutate()}
          />
          <OpenOrdersCard orders={data.open_orders} />
        </>
      )}

      <Modal
        open={pending !== null}
        onClose={() => setPending(null)}
        title={
          pending?.action === 'restore'
            ? 'Confirm restore'
            : pending?.action === 'writeoff'
              ? 'Confirm write-off'
              : 'Confirm flatten'
        }
      >
        {pending && (
          <ConfirmAction
            action={pending.action}
            targets={pending.targets}
            onCancel={() => setPending(null)}
            onConfirm={confirm}
          />
        )}
      </Modal>
    </section>
  );
}

export default AdminPage;
