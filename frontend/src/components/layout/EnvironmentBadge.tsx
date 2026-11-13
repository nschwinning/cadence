import { useEnvironment } from '../../api/system';
import type { EnvironmentStatus } from '../../types/api';

/** Badge text and style for one environment state. */
function badgeFor(env: EnvironmentStatus): { label: string; className: string; warning: boolean } {
  if (env.mismatch) {
    return {
      label: 'Account mismatch — trading blocked',
      className: 'bg-amber-100 text-amber-900 ring-1 ring-amber-300',
      warning: true,
    };
  }
  if (env.account_mode === 'live' && !env.trading_enabled) {
    return {
      label: 'Live — trading disabled',
      className: 'bg-amber-100 text-amber-900 ring-1 ring-amber-300',
      warning: true,
    };
  }
  if (env.account_mode === 'live') {
    // Red is reserved for real money.
    return {
      label: `${env.environment} · Live`,
      className: 'bg-red-600 text-white',
      warning: false,
    };
  }
  if (env.account_mode === 'paper') {
    return {
      label: `${env.environment} · Paper`,
      className: 'bg-slate-100 text-slate-700',
      warning: false,
    };
  }
  return {
    label: `${env.environment} · account unknown`,
    className: 'text-slate-300 ring-1 ring-slate-400',
    warning: false,
  };
}

/**
 * The deployment's environment and verified account mode, shown in the header on every
 * page. One colour per meaning: grey paper, solid red live, amber warning when trading is
 * blocked, grey outline while the account can't be verified. Hidden until loaded.
 */
export function EnvironmentBadge() {
  const { data } = useEnvironment();
  if (!data) return null;
  const { label, className, warning } = badgeFor(data);
  const title = data.reason ?? `${data.environment} deployment on a ${data.account_mode} account`;
  return (
    <span
      role="status"
      title={title}
      data-testid="environment-badge"
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold ${className}`}
    >
      {warning && <span aria-hidden="true">⚠</span>}
      {label}
    </span>
  );
}

export default EnvironmentBadge;
