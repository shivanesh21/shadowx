/**
 * MetricsDashboard.tsx — Per-run metrics cards + aggregate charts.
 *
 * Uses only native SVG (no Recharts import needed here) so the bundle stays
 * lean. If Recharts is already in package.json it can be swapped in later.
 */

import React, { useEffect, useState } from 'react';
import { fetchMetrics } from '../api/client';
import { MetricsResponse } from '../types';
import { RefreshCw, TrendingUp, CheckCircle2, XCircle, Zap, Clock, DollarSign, Bug } from 'lucide-react';

// ---------------------------------------------------------------------------
// Tiny stat card
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
  icon: React.ReactNode;
}

const StatCard: React.FC<StatCardProps> = ({ label, value, sub, color = 'text-white', icon }) => (
  <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-start gap-3">
    <div className="p-2 rounded-lg bg-gray-800">{icon}</div>
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-wider text-gray-500 font-semibold">{label}</p>
      <p className={`text-xl font-bold mt-0.5 ${color}`}>{value}</p>
      {sub && <p className="text-[11px] text-gray-500 mt-0.5">{sub}</p>}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Mini bar chart (pure SVG)
// ---------------------------------------------------------------------------

interface BarDatum { label: string; value: number; color: string }

const MiniBarChart: React.FC<{ data: BarDatum[]; title: string }> = ({ data, title }) => {
  const max = Math.max(...data.map((d) => d.value), 1);
  const W = 280, H = 80, padLeft = 8, barW = Math.max(8, (W - padLeft) / data.length - 4);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-xs font-semibold text-gray-400 mb-3">{title}</p>
      {data.length === 0 ? (
        <p className="text-xs text-gray-600 py-4 text-center">No data yet</p>
      ) : (
        <svg width="100%" viewBox={`0 0 ${W} ${H + 24}`} className="overflow-visible">
          {data.map((d, i) => {
            const bh = Math.max(2, (d.value / max) * H);
            const x = padLeft + i * ((W - padLeft) / data.length);
            const y = H - bh;
            return (
              <g key={i}>
                <rect x={x} y={y} width={barW} height={bh} rx={2} fill={d.color} opacity={0.85} />
                <text x={x + barW / 2} y={H + 14} textAnchor="middle" fontSize={9} fill="#6b7280">
                  {d.label.length > 6 ? d.label.slice(0, 6) : d.label}
                </text>
                <title>{`${d.label}: ${d.value}`}</title>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const MetricsDashboard: React.FC = () => {
  const [data, setData]     = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchMetrics()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const agg = data?.aggregates;
  const runs = data?.runs ?? [];

  // Build bar chart data for the last 10 runs (token counts)
  const tokenBars: BarDatum[] = runs
    .slice(0, 10)
    .reverse()
    .map((r) => ({
      label: r.run_id.slice(-6),
      value: (r as any).total_tokens ?? r.tokens ?? 0,
      color: r.status === 'done' ? '#6366f1' : r.status === 'failed' ? '#f43f5e' : '#f59e0b',
    }));

  const durationBars: BarDatum[] = runs
    .slice(0, 10)
    .reverse()
    .map((r) => ({
      label: r.run_id.slice(-6),
      value: Math.round((r as any).duration_seconds ?? 0),
      color: '#22d3ee',
    }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white">Metrics Dashboard</h2>
          <p className="text-xs text-gray-400 mt-0.5">Aggregate statistics across all factory runs</p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-950/40 border border-rose-800/50 p-4 text-sm text-rose-300">{error}</div>
      )}

      {loading && !error && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1,2,3,4].map((i) => <div key={i} className="h-24 rounded-xl bg-gray-900 animate-pulse" />)}
        </div>
      )}

      {!loading && agg && (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              label="Total Runs"
              value={data!.total_runs}
              icon={<TrendingUp className="w-4 h-4 text-indigo-400" />}
            />
            <StatCard
              label="Success Rate"
              value={`${Math.round(agg.success_rate * 100)}%`}
              sub={`${agg.total_done} done / ${agg.total_failed} failed`}
              color={agg.success_rate >= 0.8 ? 'text-emerald-400' : agg.success_rate >= 0.5 ? 'text-amber-400' : 'text-rose-400'}
              icon={<CheckCircle2 className="w-4 h-4 text-emerald-400" />}
            />
            <StatCard
              label="Avg Tokens"
              value={agg.avg_tokens.toLocaleString()}
              color="text-indigo-300"
              icon={<Zap className="w-4 h-4 text-indigo-400" />}
            />
            <StatCard
              label="Total Cost"
              value={`$${agg.total_cost_usd.toFixed(4)}`}
              sub={`avg $${agg.avg_cost_usd.toFixed(4)} / run`}
              color="text-emerald-400"
              icon={<DollarSign className="w-4 h-4 text-emerald-400" />}
            />
            <StatCard
              label="Avg Duration"
              value={`${agg.avg_duration_seconds}s`}
              color="text-cyan-300"
              icon={<Clock className="w-4 h-4 text-cyan-400" />}
            />
            <StatCard
              label="Cancelled"
              value={agg.total_cancelled}
              icon={<XCircle className="w-4 h-4 text-amber-400" />}
            />
            <StatCard
              label="Avg Tests Passed"
              value={agg.avg_tests_passed ?? '—'}
              color="text-emerald-300"
              icon={<CheckCircle2 className="w-4 h-4 text-emerald-400" />}
            />
            <StatCard
              label="Avg Debug Iters"
              value={agg.avg_debug_iterations ?? '—'}
              color="text-amber-300"
              icon={<Bug className="w-4 h-4 text-amber-400" />}
            />
          </div>

          {/* Mini charts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <MiniBarChart data={tokenBars} title="Token usage per run (last 10, newest right)" />
            <MiniBarChart data={durationBars} title="Duration (s) per run (last 10, newest right)" />
          </div>

          {/* Per-run table (mini) */}
          {runs.length > 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-800">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Recent runs</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-800 text-[10px] uppercase tracking-wider text-gray-600">
                      <th className="px-4 py-2 text-left">Run ID</th>
                      <th className="px-4 py-2 text-left">Idea</th>
                      <th className="px-4 py-2 text-center">Status</th>
                      <th className="px-4 py-2 text-right">Tokens</th>
                      <th className="px-4 py-2 text-right">Duration</th>
                      <th className="px-4 py-2 text-right">Cost</th>
                      <th className="px-4 py-2 text-right">Tests</th>
                      <th className="px-4 py-2 text-right">Debug Iters</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60">
                    {runs.map((r) => (
                      <tr key={r.run_id} className="hover:bg-gray-800/30 transition-colors">
                        <td className="px-4 py-2 font-mono text-gray-500">#{r.run_id.slice(-8)}</td>
                        <td className="px-4 py-2 text-gray-300 max-w-[200px] truncate">{r.idea}</td>
                        <td className="px-4 py-2 text-center">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                            r.status === 'done'      ? 'bg-emerald-900/60 text-emerald-400' :
                            r.status === 'failed'   ? 'bg-rose-900/60 text-rose-400'    :
                            r.status === 'running'  ? 'bg-indigo-900/60 text-indigo-400' :
                                                       'bg-gray-800 text-gray-400'
                          }`}>{r.status}</span>
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-indigo-300">
                          {((r as any).total_tokens ?? r.tokens ?? 0).toLocaleString()}
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-cyan-300">
                          {(r as any).duration_seconds ? `${Math.round((r as any).duration_seconds)}s` : '—'}
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-emerald-400">
                          {r.cost_usd ? `$${r.cost_usd.toFixed(4)}` : '—'}
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-gray-400">
                          {(r as any).tests_passed ?? '—'}/{(r as any).total_tests ?? '—'}
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-amber-400">
                          {(r as any).debug_iterations ?? 0}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {!loading && !error && data?.total_runs === 0 && (
        <div className="rounded-xl border border-dashed border-gray-700 p-10 text-center text-gray-500">
          <TrendingUp className="w-8 h-8 mx-auto mb-3 opacity-40" />
          <p className="text-sm font-medium">No metrics yet</p>
          <p className="text-xs mt-1">Complete a factory run to see stats here.</p>
        </div>
      )}
    </div>
  );
};
