import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useStrategies } from '../../api/bots';
import { EChart } from '../../components/charts/EChart';
import { buildCrossoverChartOption } from './crossoverChart';

/** Strategy key whose explanation this page highlights. */
const MA_CROSSOVER = 'ma_crossover';

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

function IllustrativeChart() {
  const option = useMemo(() => buildCrossoverChartOption(), []);
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-base font-semibold text-slate-900">
        How the crossover works
      </h2>
      <p className="mt-1 text-xs text-slate-500">
        Illustrative only — synthetic data. The bot enters when the fast SMA
        crosses above the slow SMA (green) and exits when it crosses back below
        (red).
      </p>
      <div className="mt-3">
        <EChart
          option={option}
          height={260}
          className="w-full"
          ariaLabel="Illustrative moving-average crossover with entry and exit markers"
        />
      </div>
    </div>
  );
}

export function StrategiesPage() {
  const { data, isPending, isError } = useStrategies();
  const maCrossover = data?.find((s) => s.key === MA_CROSSOVER);

  return (
    <section className="flex flex-col gap-6">
      <BackLink />
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Strategy guide
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          How the deterministic bot strategy and its risk controls work.
        </p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-base font-semibold text-slate-900">
          {maCrossover?.display_name ?? 'MA Crossover'}
        </h2>
        {isPending && (
          <p role="status" aria-live="polite" className="mt-2 text-sm text-slate-500">
            Loading strategy details…
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
        {!isPending && !isError && (
          <p className="mt-2 whitespace-pre-line text-sm text-slate-700">
            {maCrossover?.explanation ??
              'No explanation is available for this strategy.'}
          </p>
        )}
      </div>

      <IllustrativeChart />

      <div>
        <h2 className="text-base font-semibold text-slate-900">Risk controls</h2>
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
