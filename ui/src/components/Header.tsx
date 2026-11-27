import React from 'react';
import { Cpu, Play, Clock, Zap, Activity } from 'lucide-react';
import { RunState } from '../types';

interface HeaderProps {
  activeView: 'launch' | 'run' | 'history';
  onNavigate: (view: 'launch' | 'run' | 'history') => void;
  runState: RunState | null;
  elapsedSeconds: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeView,
  onNavigate,
  runState,
  elapsedSeconds,
}) => {
  const formatTime = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${mins.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const getStatusBadge = () => {
    if (!runState) return null;
    const status = runState.status;
    if (status === 'running') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-950/80 text-indigo-400 border border-indigo-700/50">
          <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse-fast" />
          RUNNING ({runState.current_stage})
        </span>
      );
    }
    if (status === 'done') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-950/80 text-emerald-400 border border-emerald-700/50">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          COMPLETED
        </span>
      );
    }
    if (status === 'failed') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-950/80 text-rose-400 border border-rose-700/50">
          <span className="w-2 h-2 rounded-full bg-rose-500" />
          FAILED
        </span>
      );
    }
    if (status === 'cancelled') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-950/80 text-amber-400 border border-amber-700/50">
          CANCELLED
        </span>
      );
    }
    return null;
  };

  return (
    <header className="sticky top-0 z-40 w-full border-b border-gray-800 bg-gray-950/85 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Left: Branding */}
        <div className="flex items-center gap-6">
          <div
            onClick={() => onNavigate('launch')}
            className="flex items-center gap-2.5 cursor-pointer group"
          >
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-indigo-600 to-cyan-500 flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:shadow-indigo-500/40 transition-shadow">
              <Cpu className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-base tracking-tight bg-gradient-to-r from-white via-gray-200 to-indigo-300 bg-clip-text text-transparent">
                  ShadowX Factory
                </span>
                <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-indigo-900/60 text-indigo-300 border border-indigo-700/40">
                  Agentic SDLC
                </span>
              </div>
              <p className="text-[11px] text-gray-400 leading-none">
                Autonomous Multi-Agent Software Factory
              </p>
            </div>
          </div>

          {/* Navigation links */}
          <nav className="hidden md:flex items-center gap-1 ml-4 border-l border-gray-800 pl-4">
            <button
              onClick={() => onNavigate('launch')}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeView === 'launch'
                  ? 'bg-gray-800 text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-900'
              }`}
            >
              <span className="flex items-center gap-1.5">
                <Play className="w-3.5 h-3.5" /> Launch
              </span>
            </button>
            <button
              onClick={() => onNavigate('run')}
              disabled={!runState}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                activeView === 'run'
                  ? 'bg-gray-800 text-white'
                  : !runState
                  ? 'text-gray-600 cursor-not-allowed'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-900'
              }`}
            >
              <span className="flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5" /> Run View
              </span>
            </button>
          </nav>
        </div>

        {/* Right: Telemetry counters & active run pill */}
        <div className="flex items-center gap-4">
          {runState && (
            <div className="flex items-center gap-3 text-xs text-gray-400">
              {getStatusBadge()}

              <div className="hidden sm:flex items-center gap-1 bg-gray-900 border border-gray-800 px-2.5 py-1 rounded-md font-mono">
                <Clock className="w-3.5 h-3.5 text-gray-500" />
                <span>{formatTime(elapsedSeconds)}</span>
              </div>

              <div className="hidden sm:flex items-center gap-1 bg-gray-900 border border-gray-800 px-2.5 py-1 rounded-md font-mono">
                <Zap className="w-3.5 h-3.5 text-indigo-400" />
                <span>{runState.tokens.toLocaleString()} tok</span>
                {runState.cost_usd !== undefined && runState.cost_usd > 0 && (
                  <span className="text-emerald-400 ml-1">(${runState.cost_usd.toFixed(4)})</span>
                )}
              </div>

              <span className="hidden lg:inline text-[11px] font-mono text-gray-500">
                #{runState.run_id.slice(-8)}
              </span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
