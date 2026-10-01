import { useTechnicalIndicatorConfig } from '../../api/technicalIndicators';
import type {
  GateCondition,
  IndicatorInfo,
  ReversalFlagInfo,
} from '../../types/api';

/** Render an indicator's parameters as a compact `name value` list. */
function paramsLabel(indicator: IndicatorInfo): string {
  if (indicator.params.length === 0) return '—';
  return indicator.params.map((p) => `${p.name} ${p.value}`).join(', ');
}

/** One gate condition row: its description and threshold (or em dash). */
function GateConditionRow({ condition }: { condition: GateCondition }) {
  return (
    <li className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-slate-700">{condition.description}</span>
      <span className="shrink-0 tabular-nums text-slate-500">
        {condition.threshold === null ? '—' : condition.threshold}
      </span>
    </li>
  );
}

/** A titled card wrapper used for each grouped section. */
function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 p-4">
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function ReversalFlagRow({ flag }: { flag: ReversalFlagInfo }) {
  return (
    <li className="py-2">
      <p className="font-medium text-slate-800">{flag.label}</p>
      <p className="mt-0.5 text-sm text-slate-600">{flag.description}</p>
    </li>
  );
}

/**
 * Technical Indicators — read-only view of the configured strategy setup: the
 * computed indicator set with its period/lookback parameters, the deterministic
 * uptrend trend-gate rules and thresholds, and the reversal-flag definitions.
 * All content is fetched from the backend so it stays truthful if the strategy
 * constants change. Info-only: nothing here is editable.
 */
export function TechnicalIndicatorsPage() {
  const { data, isPending, isError } = useTechnicalIndicatorConfig();

  return (
    <section className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Technical Indicators
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          The configured indicator set, uptrend trend-gate rules, and reversal
          flags used by the nightly strategy. Read-only.
        </p>
      </div>

      {isPending && (
        <p role="status" aria-live="polite" className="text-slate-500">
          Loading configuration…
        </p>
      )}

      {isError && (
        <div
          role="alert"
          className="rounded border border-red-300 bg-red-50 p-4 text-red-800"
        >
          <p className="font-semibold">Could not load the configuration</p>
          <p className="mt-1 text-sm">Please try again later.</p>
        </div>
      )}

      {!isPending && !isError && data && (
        <>
          <SectionCard title="Indicator set">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <th className="px-3 py-2">Indicator</th>
                    <th className="px-3 py-2">Parameters</th>
                  </tr>
                </thead>
                <tbody>
                  {data.indicators.map((indicator) => (
                    <tr
                      key={indicator.key}
                      className="border-b border-slate-100"
                    >
                      <td className="px-3 py-2 font-medium text-slate-800">
                        {indicator.label}
                      </td>
                      <td className="px-3 py-2 tabular-nums text-slate-600">
                        {paramsLabel(indicator)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard title="Trend gate">
            <p className="text-sm text-slate-600">
              {data.trend_gate.description}
            </p>

            <h3 className="mt-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Regime
            </h3>
            <ul className="m-0 list-none divide-y divide-slate-100 p-0">
              {data.trend_gate.regime.map((c) => (
                <GateConditionRow key={c.description} condition={c} />
              ))}
            </ul>

            <h3 className="mt-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Momentum
            </h3>
            <ul className="m-0 list-none divide-y divide-slate-100 p-0">
              {data.trend_gate.momentum.map((c) => (
                <GateConditionRow key={c.description} condition={c} />
              ))}
            </ul>

            <dl className="mt-4 space-y-2 text-sm">
              <div>
                <dt className="font-medium text-slate-700">OBV bonus</dt>
                <dd className="text-slate-600">{data.trend_gate.obv_bonus}</dd>
              </div>
              <div>
                <dt className="font-medium text-slate-700">
                  Missing indicator
                </dt>
                <dd className="text-slate-600">
                  {data.trend_gate.missing_indicator_rule}
                </dd>
              </div>
            </dl>
          </SectionCard>

          <SectionCard title="Reversal flags">
            <ul className="m-0 list-none divide-y divide-slate-100 p-0">
              {data.reversal_flags.flags.map((flag) => (
                <ReversalFlagRow key={flag.key} flag={flag} />
              ))}
            </ul>
            <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-2 text-sm">
              <div>
                <dt className="font-medium text-slate-700">RSI overbought</dt>
                <dd className="tabular-nums text-slate-600">
                  {data.reversal_flags.rsi_overbought}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-slate-700">
                  Slope-flatten epsilon
                </dt>
                <dd className="tabular-nums text-slate-600">
                  {data.reversal_flags.slope_flatten_eps}
                </dd>
              </div>
            </dl>
          </SectionCard>
        </>
      )}
    </section>
  );
}

export default TechnicalIndicatorsPage;
