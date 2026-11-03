import { Link } from 'react-router-dom';
import { useStrategies } from '../../api/bots';
import type { BotStrategyCatalogEntry } from '../../types/api';

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

/** One documented risk control: a heading and its description. */
function RiskControl({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 text-sm text-slate-600">{children}</p>
    </div>
  );
}

/** A short one-line blurb derived from a strategy's explanation (its first sentence). */
function strategyBlurb(explanation: string): string {
  const trimmed = explanation.trim();
  const sentenceEnd = trimmed.indexOf('. ');
  if (sentenceEnd !== -1) return trimmed.slice(0, sentenceEnd + 1);
  return trimmed.split('\n')[0];
}

/** A catalog strategy rendered as a card linking to its own detail page. */
function StrategyCard({ strategy }: { strategy: BotStrategyCatalogEntry }) {
  return (
    <Link
      to={`/bots/strategies/${strategy.key}`}
      className="flex flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-emerald-300 hover:shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
    >
      <h2 className="text-base font-semibold text-slate-900">
        {strategy.display_name}
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        {strategyBlurb(strategy.explanation)}
      </p>
      <span className="mt-3 text-sm font-medium text-emerald-700">
        View strategy →
      </span>
    </Link>
  );
}

/**
 * Strategy guide **index**: lists every strategy in the bots catalog as a card
 * linking to its own detail page, plus a shared "Capital & risk" section that
 * documents the strategy-agnostic capital and risk controls once (not repeated on
 * the individual strategy pages).
 */
export function StrategiesPage() {
  const { data, isPending, isError } = useStrategies();
  const strategies = data ?? [];

  return (
    <section className="flex flex-col gap-6">
      <BackLink />
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Strategy guide
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Browse the deterministic bot strategies and how the shared capital
          controls work.
        </p>
      </div>

      <div>
        <h2 className="text-base font-semibold text-slate-900">Strategies</h2>
        {isPending && (
          <p
            role="status"
            aria-live="polite"
            className="mt-2 text-sm text-slate-500"
          >
            Loading strategies…
          </p>
        )}
        {isError && (
          <p
            role="alert"
            className="mt-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
          >
            Could not load the strategy catalog. Please try again later.
          </p>
        )}
        {!isPending && !isError && strategies.length === 0 && (
          <p className="mt-2 text-sm text-slate-500">
            No strategies are registered yet.
          </p>
        )}
        {!isPending && !isError && strategies.length > 0 && (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {strategies.map((strategy) => (
              <StrategyCard key={strategy.key} strategy={strategy} />
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-base font-semibold text-slate-900">Capital & risk</h2>
        <p className="mt-1 text-sm text-slate-500">
          These apply across the shared capital pool, regardless of strategy.
        </p>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <RiskControl title="Shared budget ceiling">
            All positions draw from one capital pool. A buy executes only if it
            fits in the remaining cash, so total deployed capital can never exceed
            the bot's initial capital no matter how many names signal.
          </RiskControl>
          <RiskControl title="ATR position sizing">
            Each position targets an equal dollar risk: shares ≈ (budget × risk %)
            ÷ (k × ATR), using the Average True Range of the symbol's recent bars.
            Higher volatility means a smaller position.
          </RiskControl>
          <RiskControl title="Per-name cap">
            No single position may exceed a set fraction of the budget, so the pool
            stays diversified even when one name sizes large.
          </RiskControl>
          <RiskControl title="Max concurrent positions">
            The bot holds at most N names at once. When more than N signal, the
            lowest tickers alphabetically win — a deterministic tie-break.
          </RiskControl>
          <RiskControl title="Take-profit / stop-loss">
            Optional per-position exits: sell once a position rises above or falls
            below the entry price by the configured percentage, regardless of the
            strategy signal.
          </RiskControl>
          <RiskControl title="Drawdown kill-switch">
            If the whole bot's value falls far enough from its peak, it liquidates
            every position and stops opening new ones.
          </RiskControl>
        </div>
      </div>
    </section>
  );
}

export default StrategiesPage;
