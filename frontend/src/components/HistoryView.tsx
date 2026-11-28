/**
 * HistoryView.tsx — Run history table with status badges, duration, tokens,
 * cost, and per-row action buttons (view run, download ZIP).
 */

import React, { useEffect, useState } from 'react';
import { fetchRuns } from '../api/client';
import { RunState } from '../types';
import { RefreshCw, Download, Eye, CheckCircle2, XCircle, Ban, Loader2, Clock, Zap, DollarSign, Play } from 'lucide-react';

interface HistoryViewProps {
  /** Called when the user clicks "View Run" for a finished run. */
  onViewRun: (run: RunState) => void;
  /** Called to trigger a new run from an idea in history. */
  onRerun?: (idea: string) => void;
  /** Called to start interactive event replay of a run. */
  onReplayRun?: (run: RunState) => void;
}

const STATUS_STYLES: Record<string, string> = {
  done:      'bg-emerald-950/80 text-emerald-400 border-emerald-700/50',
  failed:    'bg-rose-950/80    text-rose-400    border-rose-700/50',
  cancelled: 'bg-amber-950/80  text-amber-400   border-amber-700/50',
  running:   'bg-indigo-950/80 text-indigo-400  border-indigo-700/50',
  pending:   'bg-gray-800      text-gray-400    border-gray-700',
};

const StatusIcon: React.FC<{ status: string }> = ({ status }) => {
  if (status === 'done')      return <CheckCircle2 className="w-3.5 h-3.5" />;
  if (status === 'failed')    return <XCircle       className="w-3.5 h-3.5" />;
  if (status === 'cancelled') return <Ban           className="w-3.5 h-3.5" />;
  return <Loader2 className="w-3.5 h-3.5 animate-spin" />;
};

function fmtDuration(secs: number | undefined): string {
  if (!secs) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return `${m}m ${s}s`;
}

function fmtDate(ts: number | undefined): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export const HistoryView: React.FC<HistoryViewProps> = ({ onViewRun, onRerun, onReplayRun }) => {
  const [runs, setRuns]     = useState<RunState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchRuns()
      .then(setRuns)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white">Run History</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {runs.length} run{runs.length !== 1 ? 's' : ''} recorded
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl bg-rose-950/40 border border-rose-800/50 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !error && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-xl bg-gray-900 animate-pulse" />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && runs.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-700 p-10 text-center text-gray-500">
          <Clock className="w-8 h-8 mx-auto mb-3 opacity-40" />
          <p className="text-sm font-medium">No runs yet</p>
          <p className="text-xs mt-1">Start a factory run from the Launch screen.</p>
        </div>
      )}

      {/* Table */}
      {!loading && runs.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-900/80 border-b border-gray-800 text-[11px] uppercase tracking-wider text-gray-500">
                <th className="px-4 py-3 text-left font-semibold">Status</th>
                <th className="px-4 py-3 text-left font-semibold">Idea</th>
                <th className="px-4 py-3 text-left font-semibold">Stage</th>
                <th className="px-4 py-3 text-right font-semibold">
                  <span className="flex items-center justify-end gap-1"><Clock className="w-3 h-3" /> Duration</span>
                </th>
                <th className="px-4 py-3 text-right font-semibold">
                  <span className="flex items-center justify-end gap-1"><Zap className="w-3 h-3" /> Tokens</span>
                </th>
                <th className="px-4 py-3 text-right font-semibold">
                  <span className="flex items-center justify-end gap-1"><DollarSign className="w-3 h-3" /> Cost</span>
                </th>
                <th className="px-4 py-3 text-left font-semibold">Started</th>
                <th className="px-4 py-3 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {runs.map((run) => (
                <tr key={run.run_id} className="hover:bg-gray-900/40 transition-colors group">
                  {/* Status */}
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                        STATUS_STYLES[run.status] ?? STATUS_STYLES.pending
                      }`}
                    >
                      <StatusIcon status={run.status} />
                      {run.status.toUpperCase()}
                    </span>
                  </td>

                  {/* Idea */}
                  <td className="px-4 py-3 max-w-xs">
                    <span className="text-gray-200 font-medium line-clamp-1 text-xs" title={run.idea}>
                      {run.idea}
                    </span>
                    <span className="font-mono text-[10px] text-gray-500">#{run.run_id.slice(-8)}</span>
                  </td>

                  {/* Stage */}
                  <td className="px-4 py-3 text-xs text-gray-400 font-mono">{run.current_stage}</td>

                  {/* Duration */}
                  <td className="px-4 py-3 text-right text-xs font-mono text-gray-300">
                    {fmtDuration((run as any).duration_seconds)}
                  </td>

                  {/* Tokens */}
                  <td className="px-4 py-3 text-right text-xs font-mono text-indigo-300">
                    {(run.tokens || 0).toLocaleString()}
                  </td>

                  {/* Cost */}
                  <td className="px-4 py-3 text-right text-xs font-mono text-emerald-400">
                    {run.cost_usd ? `$${run.cost_usd.toFixed(4)}` : '—'}
                  </td>

                  {/* Date */}
                  <td className="px-4 py-3 text-xs text-gray-500">{fmtDate(run.created_at)}</td>

                  {/* Actions */}
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => onViewRun(run)}
                        className="p-1.5 rounded-md bg-indigo-900/60 text-indigo-300 hover:bg-indigo-800 border border-indigo-700/50 transition-colors"
                        title="View run"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                      {onReplayRun && (
                        <button
                          onClick={() => onReplayRun(run)}
                          className="p-1.5 rounded-md bg-purple-900/60 text-purple-300 hover:bg-purple-800 border border-purple-700/50 transition-colors"
                          title="Interactive Replay"
                        >
                          <Play className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <a
                        href={`/runs/${run.run_id}/zip`}
                        download
                        className="p-1.5 rounded-md bg-gray-800 text-gray-300 hover:bg-gray-700 border border-gray-700 transition-colors"
                        title="Download workspace ZIP"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </a>
                      {onRerun && (
                        <button
                          onClick={() => onRerun(run.idea)}
                          className="p-1.5 rounded-md bg-emerald-900/60 text-emerald-300 hover:bg-emerald-800 border border-emerald-700/50 transition-colors"
                          title="Re-run this idea"
                        >
                          <RefreshCw className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
