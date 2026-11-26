import React, { useState } from 'react';
import {
  Terminal,
  ChevronDown,
  ChevronRight,
  Sparkles,
  Bot,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { AgentMessageEvent, ToolCallEvent, ToolResultEvent } from '../types';

interface AgentPanelProps {
  currentRole: string;
  messages: AgentMessageEvent[];
  tools: Array<{
    call: ToolCallEvent;
    result?: ToolResultEvent;
  }>;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({
  currentRole,
  messages,
  tools,
}) => {
  const [expandedTools, setExpandedTools] = useState<Record<number, boolean>>({});

  const toggleTool = (idx: number) => {
    setExpandedTools((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  const latestMessage = messages.length > 0 ? messages[messages.length - 1] : null;

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-5 shadow-xl backdrop-blur-sm flex flex-col h-[520px]">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-gray-800 mb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-900/60 border border-indigo-700/50 flex items-center justify-center text-indigo-400">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs text-gray-400 uppercase font-semibold">
              Active Agent
            </div>
            <div className="text-sm font-bold text-white flex items-center gap-1.5">
              <span>{currentRole || 'Orchestrator'}</span>
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            </div>
          </div>
        </div>

        <div className="text-xs text-gray-500 font-mono">
          {tools.length} tool calls
        </div>
      </div>

      {/* Stream & History */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {/* Current / Latest Agent Thought Bubble */}
        {latestMessage && (
          <div className="p-3.5 rounded-lg bg-indigo-950/40 border border-indigo-800/40 text-sm">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-300 mb-1.5">
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              <span>{latestMessage.agent_name} commentary</span>
            </div>
            <p className="text-xs text-gray-200 leading-relaxed font-sans whitespace-pre-wrap">
              {latestMessage.content}
            </p>
          </div>
        )}

        {/* Collapsible Tool Call Log */}
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 mb-2 flex items-center gap-1.5">
            <Terminal className="w-3.5 h-3.5 text-cyan-400" />
            <span>Tool Executions & Results</span>
          </div>

          {tools.length === 0 ? (
            <div className="text-center py-8 text-xs text-gray-500">
              No tool calls yet. Waiting for stage execution...
            </div>
          ) : (
            <div className="space-y-2">
              {tools.map((item, idx) => {
                const isExpanded = !!expandedTools[idx];
                const hasResult = !!item.result;
                const isError = item.result?.error;

                return (
                  <div
                    key={idx}
                    className="rounded-lg border border-gray-800 bg-gray-950/70 overflow-hidden text-xs"
                  >
                    {/* Tool Bar Header */}
                    <button
                      onClick={() => toggleTool(idx)}
                      className="w-full px-3 py-2 flex items-center justify-between text-left hover:bg-gray-900/60 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        {isExpanded ? (
                          <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
                        )}
                        <span className="font-mono font-semibold text-cyan-300">
                          {item.call.tool_name}()
                        </span>
                        {item.call.agent_name && (
                          <span className="text-[10px] text-gray-500 px-1.5 py-0.5 rounded bg-gray-900 border border-gray-800">
                            {item.call.agent_name}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {hasResult ? (
                          isError ? (
                            <span className="flex items-center gap-1 text-[11px] text-rose-400">
                              <XCircle className="w-3.5 h-3.5" /> Error
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-[11px] text-emerald-400">
                              <CheckCircle className="w-3.5 h-3.5" /> OK
                            </span>
                          )
                        ) : (
                          <span className="text-[11px] text-amber-400">Running...</span>
                        )}
                      </div>
                    </button>

                    {/* Expanded details */}
                    {isExpanded && (
                      <div className="p-3 border-t border-gray-800/80 bg-black/40 font-mono text-[11px] space-y-2">
                        <div>
                          <div className="text-[10px] text-gray-500 uppercase font-bold mb-1">
                            Arguments:
                          </div>
                          <pre className="p-2 rounded bg-gray-950 text-gray-300 overflow-x-auto whitespace-pre-wrap">
                            {JSON.stringify(item.call.arguments, null, 2)}
                          </pre>
                        </div>

                        {item.result && (
                          <div>
                            <div className="text-[10px] text-gray-500 uppercase font-bold mb-1">
                              Result:
                            </div>
                            <pre className="p-2 rounded bg-gray-950 text-emerald-300 overflow-x-auto max-h-40 whitespace-pre-wrap">
                              {typeof item.result.result === 'string'
                                ? item.result.result
                                : JSON.stringify(item.result.result, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
