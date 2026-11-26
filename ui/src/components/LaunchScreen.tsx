import React, { useState } from 'react';
import { Rocket, Sparkles, Shield, Cpu, RefreshCw, Terminal, Layers } from 'lucide-react';
import { StartRunParams } from '../types';

interface LaunchScreenProps {
  onStart: (params: StartRunParams) => void;
  isStarting: boolean;
  error: string | null;
}

const PRESET_IDEAS = [
  {
    title: 'CLI Todo App with SQLite',
    desc: 'Terminal task tracker with SQLite persistence, tagging, priorities, and formatted output.',
    icon: Terminal,
  },
  {
    title: 'Markdown to HTML Static Site Generator',
    desc: 'Static engine converting nested markdown folders into styled HTML pages with syntax highlighting.',
    icon: Layers,
  },
  {
    title: 'Distributed Rate Limiter Library',
    desc: 'Token-bucket and sliding-window rate limiter with thread-safety and configurable quotas.',
    icon: Shield,
  },
  {
    title: 'Bank Account Ledger API',
    desc: 'Clean architecture double-entry ledger with balance verification, transactions, and audit logs.',
    icon: Cpu,
  },
  {
    title: 'Expense Tracker CLI with Budget Alerts',
    desc: 'Personal finance CLI managing categories, monthly budget caps, and tabular spend reports.',
    icon: Sparkles,
  },
];

export const LaunchScreen: React.FC<LaunchScreenProps> = ({
  onStart,
  isStarting,
  error,
}) => {
  const [idea, setIdea] = useState('');
  const [gates, setGates] = useState(false);
  const [useFake, setUseFake] = useState(true); // Default to fake provider for instant reliable zero-quota testing
  const [maxIterations, setMaxIterations] = useState(4);
  const [maxTokens, setMaxTokens] = useState(100000);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!idea.trim() || isStarting) return;
    onStart({
      idea: idea.trim(),
      gates,
      use_fake: useFake,
      max_tokens: maxTokens,
    });
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Hero section */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-950/60 border border-indigo-700/40 text-indigo-300 text-xs font-medium mb-3">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          Autonomous Multi-Agent Software Factory
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-2">
          From one-line product idea to <span className="bg-gradient-to-r from-indigo-400 to-cyan-400 bg-clip-text text-transparent">tested code & docs</span>
        </h1>
        <p className="text-sm sm:text-base text-gray-400 max-w-2xl mx-auto">
          Analyst, Architect, Developer, Tester, Debugger, Reviewer, and Documenter collaborating autonomously in isolated workspaces.
        </p>
      </div>

      {/* Main input card */}
      <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-6 shadow-2xl backdrop-blur-sm mb-6">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-300 mb-2">
              What do you want to build?
            </label>
            <div className="relative">
              <textarea
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                placeholder="e.g. Build a CLI todo app with SQLite persistence, tagging, and priority filtering..."
                rows={3}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg p-3.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all resize-none font-mono"
              />
              <div className="absolute right-3 bottom-3 text-[11px] text-gray-500">
                {idea.length} chars
              </div>
            </div>
          </div>

          {/* Quick presets */}
          <div>
            <span className="block text-xs font-medium text-gray-400 mb-2">
              Quick presets (click to fill):
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {PRESET_IDEAS.map((preset, idx) => {
                const Icon = preset.icon;
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setIdea(preset.desc)}
                    className="text-left p-3 rounded-lg bg-gray-950/60 border border-gray-800 hover:border-indigo-500/50 hover:bg-indigo-950/20 transition-all group"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Icon className="w-3.5 h-3.5 text-indigo-400 group-hover:text-cyan-400" />
                      <span className="text-xs font-semibold text-gray-200 group-hover:text-white truncate">
                        {preset.title}
                      </span>
                    </div>
                    <p className="text-[11px] text-gray-400 line-clamp-2">
                      {preset.desc}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Configuration options */}
          <div className="border-t border-gray-800 pt-5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-300 mb-3">
              Execution Options
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Approval gates switch */}
              <label className="flex items-start gap-3 p-3 rounded-lg bg-gray-950/60 border border-gray-800 cursor-pointer hover:border-gray-700">
                <input
                  type="checkbox"
                  checked={gates}
                  onChange={(e) => setGates(e.target.checked)}
                  className="mt-0.5 rounded border-gray-700 text-indigo-600 focus:ring-indigo-500"
                />
                <div>
                  <span className="text-xs font-medium text-gray-200 block">
                    Human-in-the-Loop Approval Gates
                  </span>
                  <span className="text-[11px] text-gray-400 block">
                    Pause for user review after Requirements and Design stages.
                  </span>
                </div>
              </label>

              {/* Demo mode / Fake LLM switch */}
              <label className="flex items-start gap-3 p-3 rounded-lg bg-gray-950/60 border border-gray-800 cursor-pointer hover:border-gray-700">
                <input
                  type="checkbox"
                  checked={useFake}
                  onChange={(e) => setUseFake(e.target.checked)}
                  className="mt-0.5 rounded border-gray-700 text-indigo-600 focus:ring-indigo-500"
                />
                <div>
                  <span className="text-xs font-medium text-gray-200 block">
                    Demo Mode (Mock LLM)
                  </span>
                  <span className="text-[11px] text-gray-400 block">
                    Instant, deterministic execution with no Gemini API quota needed.
                  </span>
                </div>
              </label>

              {/* Max Debug Iterations */}
              <div className="p-3 rounded-lg bg-gray-950/60 border border-gray-800">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-gray-200">
                    Max Debug Iterations
                  </span>
                  <span className="text-xs font-mono text-indigo-400">{maxIterations}</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={5}
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(Number(e.target.value))}
                  className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                />
                <span className="text-[10px] text-gray-500 block mt-1">
                  Tester ↔ Debugger repair cycle limit.
                </span>
              </div>

              {/* Token Budget */}
              <div className="p-3 rounded-lg bg-gray-950/60 border border-gray-800">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-gray-200">
                    Token Budget
                  </span>
                  <span className="text-xs font-mono text-indigo-400">{maxTokens.toLocaleString()}</span>
                </div>
                <input
                  type="range"
                  min={20000}
                  max={200000}
                  step={10000}
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(Number(e.target.value))}
                  className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                />
                <span className="text-[10px] text-gray-500 block mt-1">
                  Enforces run budget guardrail.
                </span>
              </div>
            </div>
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-700/50 text-rose-300 text-xs">
              {error}
            </div>
          )}

          {/* Submit button */}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={!idea.trim() || isStarting}
              className={`inline-flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-semibold transition-all shadow-lg ${
                !idea.trim() || isStarting
                  ? 'bg-gray-800 text-gray-500 cursor-not-allowed shadow-none'
                  : 'bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white shadow-indigo-600/20 hover:shadow-indigo-600/40 cursor-pointer'
              }`}
            >
              {isStarting ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Starting Factory Run...
                </>
              ) : (
                <>
                  <Rocket className="w-4 h-4" />
                  Start Factory Run
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
