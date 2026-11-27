/**
 * CompareView.tsx — Side-by-side run comparison.
 *
 * User picks 2–4 runs from a checklist; the component calls
 * GET /metrics/compare?run_ids=... and renders a comparison table.
 */

import React, { useEffect, useState } from 'react';
import { fetchRuns, fetchCompare } from '../api/client';
import { RunState, MetricsResponse } from '../types';
import { RefreshCw, ChevronRight, BarChart2 } from 'lucide-react';

function fmtDuration(secs: number | undefined): string {
  if (!secs) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return `${m}m ${s}s`;
}

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const cls =
    status === 'done'      ? 'bg-emerald-900/60 text-emerald-400' :
    status === 'failed'    ? 'bg-rose-900/60 text-rose-400'    :
    status === 'cancelled' ? 'bg-amber-900/60 text-amber-400'  :
                             'bg-indigo-900/60 text-indigo-400';
  return <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${cls}`}>{status}</span>;
};

// Row in the comparison table
interface CompRow { label: string; key: string; fmt?: (v: unknown, r: unknown) => string }
const ROWS: CompRow[] = [
  { label: 'Status',           key: 'status',           fmt: (v) => String(v).toUpperCase() },
  { label: 'Stage Reached',    key: 'current_stage' },
  { label: 'Duration',         key: 'duration_seconds',  fmt: (v) => fmtDuration(v as number) },
  { label: 'Total Tokens',     key: 'total_tokens',      fmt: (v) => Number(v || 0).toLocaleString() },
  { label: 'Cost (USD)',       key: 'cost_usd',          fmt: (v) => v ? `$${Number(v).toFixed(4)}` : '—' },
  { label: 'Tests Passed',     key: 'tests_passed',      fmt: (v, r) => `${v ?? '—'} / ${(r as any).total_tests ?? '—'}` },
  { label: 'Debug Iterations', key: 'debug_iterations' },
];

export const CompareView: React.FC = () => {
  const [runs, setRuns]           = useState<RunState[]>([]);
  const [selected, setSelected]   = useState<Set<string>>(new Set());
  const [comparison, setComparison] = useState<MetricsResponse | null>(null);
  const [loading, setLoading]     = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [error, setError]         = useState<string | null>(null);

  useEffect(() => {
    setListLoading(true);
    fetchRuns()
      .then(setRuns)
      .catch((e) => setError(e.message))
      .finally(() => setListLoading(false));
  }, []);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); }
      else if (next.size < 4) { next.add(id); }
      return next;
    });
    // Clear previous comparison when selection changes
    setComparison(null);
  };

  const compare = () => {
    if (selected.size < 2) return;
    setLoading(true);
    setError(null);
    fetchCompare(Array.from(selected))
      .then(setComparison)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const selectedRuns = comparison?.selected_runs ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-white">Compare Runs</h2>
        <p className="text-xs text-gray-400 mt-0.5">Select 2–4 runs to compare side-by-side</p>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-950/40 border border-rose-800/50 p-4 text-sm text-rose-300">{error}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Run picker */}
        <div className="lg:col-span-1 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Pick runs</p>
            <span className="text-[10px] text-gray-500">{selected.size}/4 selected</span>
          </div>

          {listLoading && (
            <div className="space-y-1.5">
              {[1,2,3].map((i) => <div key={i} className="h-12 rounded-lg bg-gray-900 animate-pulse" />)}
            </div>
          )}

          {!listLoading && runs.length === 0 && (
            <div className="rounded-lg border border-dashed border-gray-700 p-6 text-center text-gray-500 text-xs">
              No runs recorded yet.
            </div>
          )}

          <div className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1">
            {runs.map((run) => {
              const isSelected = selected.has(run.run_id);
              const disabled   = !isSelected && selected.size >= 4;
              return (
                <button
                  key={run.run_id}
                  onClick={() => !disabled && toggle(run.run_id)}
                  disabled={disabled}
                  className={`w-full text-left rounded-lg border p-3 transition-colors ${
                    isSelected
                      ? 'border-indigo-500 bg-indigo-950/50'
                      : disabled
                      ? 'border-gray-800 bg-gray-900/40 opacity-40 cursor-not-allowed'
                      : 'border-gray-800 bg-gray-900/60 hover:border-gray-600'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-gray-200 truncate">{run.idea}</p>
                      <p className="text-[10px] font-mono text-gray-500 mt-0.5">#{run.run_id.slice(-8)}</p>
                    </div>
                    <StatusBadge status={run.status} />
                  </div>
                </button>
              );
            })}
          </div>

          <button
            onClick={compare}
            disabled={selected.size < 2 || loading}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <ChevronRight className="w-4 h-4" />
            )}
            {loading ? 'Comparing...' : `Compare ${selected.size} run${selected.size !== 1 ? 's' : ''}`}
          </button>
        </div>

        {/* Comparison table */}
        <div className="lg:col-span-2">
          {!comparison && !loading && (
            <div className="h-full flex items-center justify-center rounded-xl border border-dashed border-gray-700 p-10 text-center text-gray-600">
              <div>
                <BarChart2 className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="text-sm">Select 2–4 runs and click Compare</p>
              </div>
            </div>
          )}

          {comparison && selectedRuns.length >= 2 && (
            <div className="overflow-x-auto rounded-xl border border-gray-800">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-900/80 border-b border-gray-800">
                    <th className="px-4 py-3 text-left text-[11px] uppercase tracking-wider text-gray-500 font-semibold w-36">
                      Metric
                    </th>
                    {selectedRuns.map((r) => (
                      <th key={r.run_id} className="px-4 py-3 text-left text-[11px] uppercase tracking-wider text-indigo-400 font-semibold">
                        #{r.run_id.slice(-8)}
                        <span className="block text-gray-500 normal-case font-normal truncate max-w-[140px]">{r.idea}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60">
                  {ROWS.map((row) => {
                    const vals = selectedRuns.map((r) => {
                      const v = (r as any)[row.key];
                      return row.fmt ? row.fmt(v, r) : (v !== undefined && v !== null ? String(v) : '—');
                    });
                    // Highlight best value: highest for tokens/tests, lowest for duration/cost
                    const numeric = vals.map((v) => parseFloat(v.replace(/[^0-9.]/g, '')));
                    const allNumeric = numeric.every((n) => !isNaN(n));
                    const bestIdx: number | null = allNumeric
                      ? (['total_tokens', 'tests_passed'].includes(row.key)
                        ? numeric.indexOf(Math.max(...numeric))
                        : ['duration_seconds', 'cost_usd', 'debug_iterations'].includes(row.key)
                          ? numeric.indexOf(Math.min(...numeric))
                          : null)
                      : null;

                    return (
                      <tr key={row.key} className="hover:bg-gray-900/30 transition-colors">
                        <td className="px-4 py-2.5 text-gray-500 font-medium">{row.label}</td>
                        {vals.map((v, i) => (
                          <td
                            key={i}
                            className={`px-4 py-2.5 font-mono ${
                              bestIdx === i ? 'text-emerald-400 font-bold' : 'text-gray-300'
                            }`}
                          >
                            {v}
                            {bestIdx === i && (
                              <span className="ml-1 text-[9px] text-emerald-500">★</span>
                            )}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="px-4 py-2 border-t border-gray-800 text-[10px] text-gray-600">
                ★ = best value for that metric
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
