import React, { useState } from 'react';
import {
  Activity,
  Layers,
  Terminal,
  FileCode,
  CheckCircle,
  AlertTriangle,
} from 'lucide-react';
import { FactoryEvent, EventType } from '../types';

interface EventTimelineProps {
  events: FactoryEvent[];
}

type FilterCategory = 'ALL' | 'STAGE' | 'AGENT' | 'TOOL' | 'FILE' | 'TEST';

export const EventTimeline: React.FC<EventTimelineProps> = ({ events }) => {
  const [filter, setFilter] = useState<FilterCategory>('ALL');

  const filteredEvents = events.filter((ev) => {
    if (filter === 'ALL') return true;
    if (filter === 'STAGE') {
      return ev.event_type === 'stage_started' || ev.event_type === 'stage_finished' || ev.event_type === 'run_started' || ev.event_type === 'run_finished';
    }
    if (filter === 'AGENT') return ev.event_type === 'agent_message' || ev.event_type === 'llm_call';
    if (filter === 'TOOL') return ev.event_type === 'tool_call' || ev.event_type === 'tool_result';
    if (filter === 'FILE') return ev.event_type === 'file_changed';
    if (filter === 'TEST') return ev.event_type === 'test_result';
    return true;
  });

  const getEventBadge = (type: EventType) => {
    switch (type) {
      case 'stage_started':
      case 'stage_finished':
      case 'run_started':
      case 'run_finished':
        return {
          icon: Layers,
          color: 'text-indigo-400 bg-indigo-950/60 border-indigo-700/40',
        };
      case 'tool_call':
      case 'tool_result':
        return {
          icon: Terminal,
          color: 'text-cyan-400 bg-cyan-950/60 border-cyan-700/40',
        };
      case 'file_changed':
        return {
          icon: FileCode,
          color: 'text-amber-400 bg-amber-950/60 border-amber-700/40',
        };
      case 'test_result':
        return {
          icon: CheckCircle,
          color: 'text-emerald-400 bg-emerald-950/60 border-emerald-700/40',
        };
      case 'error':
      case 'loop_detected':
        return {
          icon: AlertTriangle,
          color: 'text-rose-400 bg-rose-950/60 border-rose-700/40',
        };
      default:
        return {
          icon: Activity,
          color: 'text-gray-400 bg-gray-900 border-gray-800',
        };
    }
  };

  const renderEventDetails = (ev: FactoryEvent) => {
    switch (ev.event_type) {
      case 'stage_started':
        return (
          <span>
            Stage started: <strong className="text-white">{ev.stage}</strong> by <span className="text-indigo-400">{ev.agent_name}</span>
          </span>
        );
      case 'stage_finished':
        return (
          <span>
            Stage completed: <strong className="text-white">{ev.stage}</strong>
          </span>
        );
      case 'run_started':
        return <span>Run started for idea: <em className="text-gray-300">"{ev.idea}"</em></span>;
      case 'run_finished':
        return (
          <span>
            Run finished with status: <strong className="text-emerald-400 uppercase">{ev.status}</strong> (Tokens: {ev.total_tokens || 0})
          </span>
        );
      case 'agent_message':
        return (
          <span>
            <span className="text-indigo-400 font-semibold">{ev.agent_name}:</span> {ev.content.slice(0, 100)}...
          </span>
        );
      case 'tool_call':
        return (
          <span>
            Tool call: <code className="text-cyan-300 font-mono">{ev.tool_name}()</code>
          </span>
        );
      case 'tool_result':
        return (
          <span>
            Tool result for <code className="text-cyan-300 font-mono">{ev.tool_name}()</code>
            {ev.error && <span className="text-rose-400 ml-1">({ev.error})</span>}
          </span>
        );
      case 'file_changed':
        return (
          <span>
            File modified: <code className="text-amber-300 font-mono">{ev.path}</code>
          </span>
        );
      case 'test_result':
        return (
          <span>
            Pytest run: <span className="text-emerald-400 font-bold">{ev.passed} passed</span>,{' '}
            <span className="text-rose-400 font-bold">{ev.failed} failed</span>
          </span>
        );
      case 'approval_requested':
        return (
          <span>
            Approval requested for: <strong className="text-amber-300">{ev.stage}</strong> ({ev.artifact_name})
          </span>
        );
      case 'approval_resolved':
        return (
          <span>
            Approval resolved: <strong className="text-emerald-300 uppercase">{ev.decision}</strong>
          </span>
        );
      case 'llm_call':
        return (
          <span>
            LLM call: {ev.total_tokens || 0} tokens ({ev.latency_ms || 0}ms)
          </span>
        );
      case 'error':
        return <span className="text-rose-300">Error: {ev.message}</span>;
      default:
        return <span>Event: {ev.event_type}</span>;
    }
  };

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-5 shadow-xl backdrop-blur-sm flex flex-col h-[520px]">
      {/* Header and Filter pills */}
      <div className="pb-3 border-b border-gray-800 mb-3 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-indigo-400" />
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            Live Event Stream
          </h3>
          <span className="text-xs text-gray-500 font-mono">({events.length})</span>
        </div>

        {/* Filter pills */}
        <div className="flex items-center gap-1">
          {(['ALL', 'STAGE', 'AGENT', 'TOOL', 'FILE', 'TEST'] as FilterCategory[]).map((cat) => (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                filter === cat
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-950 text-gray-400 hover:text-gray-200'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Events List */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1 font-mono text-xs">
        {filteredEvents.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            No events recorded yet.
          </div>
        ) : (
          filteredEvents.map((ev, idx) => {
            const badge = getEventBadge(ev.event_type);
            const Icon = badge.icon;
            const timeStr = ev.timestamp
              ? new Date(ev.timestamp * 1000).toLocaleTimeString()
              : '';

            return (
              <div
                key={idx}
                className="p-2.5 rounded-lg bg-gray-950/70 border border-gray-800/80 flex items-start gap-2.5 hover:border-gray-700 transition-colors"
              >
                <div
                  className={`w-6 h-6 rounded flex items-center justify-center shrink-0 border ${badge.color}`}
                >
                  <Icon className="w-3.5 h-3.5" />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-0.5">
                    <span className="text-[10px] font-bold uppercase text-gray-400">
                      {ev.event_type.replace('_', ' ')}
                    </span>
                    {timeStr && (
                      <span className="text-[10px] text-gray-600">{timeStr}</span>
                    )}
                  </div>
                  <div className="text-gray-300 leading-snug break-words">
                    {renderEventDetails(ev)}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
