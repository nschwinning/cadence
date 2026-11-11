import { Link } from 'react-router-dom';
import { useAdminAccount } from '../../api/admin';
import { formatCurrency } from '../../lib/format';

const CARD_CLASS = 'rounded-lg border border-slate-200 bg-white shadow-sm';

/**
 * Free capital below this is flagged as low: it is the smallest capital a new bot or
 * AI portfolio can be built with (the build forms' minimum).
 */
export const LOW_CAPITAL_THRESHOLD_USD = 1_000;

/**
 * Broker account tile: the capital still usable for new bots and portfolios — the
 * shared Alpaca account's **free capital** (its cash excluding short-sale proceeds,
 * minus everything Cadence has committed), capped by Alpaca's **buying power**, since
 * the broker rejects any buy beyond that regardless of cash (e.g. when short positions
 * tie up all margin). Warns amber when that is below the smallest buildable capital,
 * red when nothing is left or buying power is gone, and red when the account holds
 * short positions.
 * Account-wide: independent of the dashboard range and the equity-chart selection.
 * Reuses the Admin page's account query (polled every minute).
 */
export function AccountStateTile() {
  const { data, isPending, isError } = useAdminAccount();

  if (isPending) {
    return (
      <div className={`${CARD_CLASS} p-4`}>
        <p role="status" className="text-sm text-slate-500">
          Loading the broker account…
        </p>
      </div>
    );
  }

  const check = data?.cash_check;
  if (isError || !data?.broker_available || !check) {
    return (
      <div className={`${CARD_CLASS} p-4`} data-testid="account-tile">
        <p className="font-semibold text-slate-900">Broker unavailable</p>
        <p className="mt-1 text-sm text-slate-500">
          {data?.reason ?? 'The broker account could not be read right now.'}
        </p>
      </div>
    );
  }

  const buyingPower = data.account?.buying_power ?? 0;
  const free = Math.min(check.difference, buyingPower);
  const shorts = (data.positions ?? []).filter((p) => p.status === 'short');
  const noBuyingPower = buyingPower <= 0;
  const noneLeft = free <= 0;
  const low = !noneLeft && free < LOW_CAPITAL_THRESHOLD_USD;

  return (
    <div className={`${CARD_CLASS} p-4`} data-testid="account-tile">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">Free capital for new bots &amp; portfolios</p>
          <p
            data-testid="free-capital"
            className={`text-2xl font-semibold tabular-nums ${
              noneLeft ? 'text-red-700' : 'text-slate-900'
            }`}
          >
            {formatCurrency(free)}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Account cash {formatCurrency(check.account_cash)} · committed by Cadence{' '}
            {formatCurrency(check.committed_total)} · buying power{' '}
            <span data-testid="buying-power">{formatCurrency(buyingPower)}</span>
          </p>
        </div>
        <Link
          to="/admin"
          className="shrink-0 text-sm font-medium text-emerald-700 hover:text-emerald-800 hover:underline"
        >
          Admin →
        </Link>
      </div>

      {(noneLeft || low || shorts.length > 0) && (
        <div className="mt-3 flex flex-col gap-2 text-sm">
          {noBuyingPower && (
            <p role="alert" className="rounded border border-red-300 bg-red-50 p-2 text-red-800">
              No buying power: Alpaca rejects every buy until margin is freed (for example by
              covering short positions).
            </p>
          )}
          {noneLeft && !noBuyingPower && (
            <p role="alert" className="rounded border border-red-300 bg-red-50 p-2 text-red-800">
              No capital left: new bots or portfolios cannot be funded.
            </p>
          )}
          {low && (
            <p role="note" className="rounded border border-amber-300 bg-amber-50 p-2 text-amber-800">
              Low capital: less than {formatCurrency(LOW_CAPITAL_THRESHOLD_USD)} is free for new
              bots or portfolios.
            </p>
          )}
          {shorts.length > 0 && (
            <p role="alert" className="rounded border border-red-300 bg-red-50 p-2 text-red-800">
              {shorts.length} short {shorts.length === 1 ? 'position' : 'positions'} worth{' '}
              {formatCurrency(check.short_proceeds)} in the account. Cadence never goes short —
              restore them on the Admin page.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default AccountStateTile;
