import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useStrategies } from '../../api/bots';
import { EChart } from '../../components/charts/EChart';
import { getStrategyChart } from './strategyCharts';

function BackLink() {
  return (
    <Link
      to="/bots/strategies"
      className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700 hover:text-emerald-800 hover:underline"
    >
      <span aria-hidden="true">←</span> Back to strategies
    </Link>
  );
}

/**
 * Per-strategy **detail** page at `/bots/strategies/:key`: resolves the catalog
 * entry by its route key and renders that strategy's explanation plus its
 * illustrative chart (when one is registered). The strategy-agnostic capital/risk
 * documentation lives only on the index, not here. An unknown key shows a
 * not-found state.
 */
export function StrategyDetailPage() {
  const { key = '' } = useParams<{ key: string }>();
  const { data, isPending, isError } = useStrategies();
  const strategy = data?.find((s) => s.key === key);
  const chart = getStrategyChart(key);
  const chartOption = useMemo(() => chart?.buildOption(), [chart]);

  return (
    <section className="flex flex-col gap-6">
      <BackLink />

      {isPending && (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-slate-500"
        >
          Loading strategy details…
        </p>
      )}

      {isError && (
        <p
          role="alert"
          className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          Could not load the strategy catalog. Please try again later.
        </p>
      )}

      {!isPending && !isError && !strategy && (
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Strategy not found
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            No strategy matches “{key}”. It may have been renamed or removed.{' '}
            <Link
              to="/bots/strategies"
              className="font-medium text-emerald-700 hover:underline"
            >
              Back to the strategy guide
            </Link>
            .
          </p>
        </div>
      )}

      {!isPending && !isError && strategy && (
        <>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {strategy.display_name}
            </h1>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
            <p className="whitespace-pre-line text-sm text-slate-700">
              {strategy.explanation}
            </p>
          </div>

          {chart && chartOption && (
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="text-base font-semibold text-slate-900">
                How it works
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Illustrative only — synthetic data.
              </p>
              <div className="mt-3">
                <EChart
                  option={chartOption}
                  height={260}
                  className="w-full"
                  ariaLabel={chart.ariaLabel}
                />
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export default StrategyDetailPage;
