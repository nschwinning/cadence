import { Link } from 'react-router-dom';
import { usePresets, useStrategies } from '../../api/bots';
import { formatPercent } from '../../lib/format';
import type { BotPreset } from '../../types/api';

/** A preset's strategy parameters as compact `name value` pairs. */
function formatParams(params: Record<string, unknown>): string {
  return Object.entries(params)
    .map(([name, value]) => `${name.replace(/_/g, ' ')} ${String(value)}`)
    .join(' · ');
}

/** A risk fraction as a percentage, or "Off" when the control is disabled. */
function formatRisk(value: number | null): string {
  return value === null ? 'Off' : formatPercent(value, value * 100 < 1 ? 1 : 0);
}

function PresetRow({ preset, strategyName }: { preset: BotPreset; strategyName: string }) {
  return (
    <tr className="border-b border-slate-100 align-top">
      <td className="px-4 py-3">
        <p className="font-semibold text-slate-900">{preset.display_name}</p>
        <p className="mt-1 max-w-md text-xs text-slate-500">{preset.description}</p>
        <p className="mt-1 font-mono text-[11px] text-slate-400">{preset.key}</p>
      </td>
      <td className="px-4 py-3">
        <Link
          to={`/bots/strategies/${preset.strategy_key}`}
          className="text-emerald-700 hover:text-emerald-800 hover:underline"
        >
          {strategyName}
        </Link>
        <p className="mt-1 text-xs text-slate-500">{preset.course_ref}</p>
      </td>
      <td className="px-4 py-3 text-xs text-slate-600">
        {formatParams(preset.strategy_params)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {formatRisk(preset.take_profit_pct)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {formatRisk(preset.stop_loss_pct)}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-slate-700">
        {formatRisk(preset.drawdown_stop_pct)}
      </td>
    </tr>
  );
}

/**
 * The read-only bot preset catalog — every configuration an orchestrator may deploy.
 * Presets are code-defined, so this only lists them.
 */
export function PresetCatalogPanel() {
  const { data: presets, isPending, isError } = usePresets();
  const { data: strategies } = useStrategies();
  const strategyNames = new Map(strategies?.map((s) => [s.key, s.display_name]));

  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 p-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-slate-900">Preset catalog</h2>
          {presets && presets.length > 0 && (
            <span className="text-sm text-slate-500">
              {presets.length} preset{presets.length === 1 ? '' : 's'}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-slate-500">
          Orchestrators deploy bots only from these presets, with the parameters and risk
          controls shown.
        </p>
      </div>

      {isPending && (
        <p role="status" aria-live="polite" className="p-6 text-slate-500">
          Loading presets…
        </p>
      )}
      {isError && (
        <div
          role="alert"
          className="m-4 rounded border border-red-300 bg-red-50 p-4 text-red-800"
        >
          <p className="font-semibold">Could not load presets</p>
          <p className="mt-1 text-sm">Please try again later.</p>
        </div>
      )}
      {presets && presets.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Preset</th>
                <th className="px-4 py-3">Strategy</th>
                <th className="px-4 py-3">Parameters</th>
                <th className="px-4 py-3 text-right">Take-profit</th>
                <th className="px-4 py-3 text-right">Stop-loss</th>
                <th className="px-4 py-3 text-right">Drawdown</th>
              </tr>
            </thead>
            <tbody>
              {presets.map((p) => (
                <PresetRow
                  key={p.key}
                  preset={p}
                  strategyName={strategyNames.get(p.strategy_key) ?? p.strategy_key}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
