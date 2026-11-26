import React, { useState, useEffect, useRef } from 'react';
import { Header } from './components/Header';
import { LaunchScreen } from './components/LaunchScreen';
import { PipelineGraph } from './components/PipelineGraph';
import { AgentPanel } from './components/AgentPanel';
import { EventTimeline } from './components/EventTimeline';
import { ApprovalModal } from './components/ApprovalModal';
import {
  RunState,
  FactoryEvent,
  AgentMessageEvent,
  ToolCallEvent,
  ToolResultEvent,
  ApprovalRequestedEvent,
  StartRunParams,
  StageName,
} from './types';
import {
  startRun,
  cancelRun,
  resolveApproval,
  fetchRun,
  subscribeToEvents,
} from './api/client';
import { Octagon, Play } from 'lucide-react';

export const App: React.FC = () => {
  const [activeView, setActiveView] = useState<'launch' | 'run' | 'history'>('launch');
  const [runState, setRunState] = useState<RunState | null>(null);
  const [events, setEvents] = useState<FactoryEvent[]>([]);
  const [agentMessages, setAgentMessages] = useState<AgentMessageEvent[]>([]);
  const [tools, setTools] = useState<Array<{ call: ToolCallEvent; result?: ToolResultEvent }>>([]);
  const [pendingApproval, setPendingApproval] = useState<ApprovalRequestedEvent | null>(null);
  const [currentRole, setCurrentRole] = useState<string>('Analyst');
  const [debugIteration, setDebugIteration] = useState<number>(0);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [isCancelling, setIsCancelling] = useState<boolean>(false);
  const [startError, setStartError] = useState<string | null>(null);

  const timerRef = useRef<number | null>(null);
  const unsubscribeRef = useRef<(() => void) | null>(null);

  // Stopwatch timer when run is active
  useEffect(() => {
    if (runState?.status === 'running') {
      if (!timerRef.current) {
        timerRef.current = window.setInterval(() => {
          setElapsedSeconds((prev) => prev + 1);
        }, 1000);
      }
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [runState?.status]);

  const handleStartRun = async (params: StartRunParams) => {
    setIsStarting(true);
    setStartError(null);
    setEvents([]);
    setAgentMessages([]);
    setTools([]);
    setPendingApproval(null);
    setElapsedSeconds(0);
    setDebugIteration(0);

    try {
      const res = await startRun(params);
      const initialRun: RunState = {
        run_id: res.run_id,
        idea: params.idea,
        current_stage: 'ANALYSIS',
        status: 'running',
        tokens: 0,
        created_at: Date.now() / 1000,
        updated_at: Date.now() / 1000,
      };
      setRunState(initialRun);
      setActiveView('run');

      // Start streaming SSE events
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
      }

      unsubscribeRef.current = subscribeToEvents(
        res.run_id,
        (event) => {
          setEvents((prev) => [...prev, event]);

          // Handle state updates based on event type
          if (event.event_type === 'stage_started') {
            setCurrentRole(event.agent_name);
            setRunState((prev) =>
              prev ? { ...prev, current_stage: event.stage, status: 'running' } : null
            );
            if (event.stage === 'DEBUGGING') {
              setDebugIteration((i) => i + 1);
            }
          } else if (event.event_type === 'stage_finished') {
            setRunState((prev) => (prev ? { ...prev, current_stage: event.stage } : null));
          } else if (event.event_type === 'run_finished') {
            setRunState((prev) =>
              prev
                ? {
                    ...prev,
                    status: event.status.toLowerCase() as any,
                    tokens: event.total_tokens || prev.tokens,
                  }
                : null
            );
          } else if (event.event_type === 'agent_message') {
            setAgentMessages((prev) => [...prev, event]);
          } else if (event.event_type === 'tool_call') {
            setTools((prev) => [...prev, { call: event }]);
          } else if (event.event_type === 'tool_result') {
            setTools((prev) => {
              if (prev.length === 0) return prev;
              const last = prev[prev.length - 1];
              const updated = { ...last, result: event };
              return [...prev.slice(0, prev.length - 1), updated];
            });
          } else if (event.event_type === 'llm_call') {
            if (event.total_tokens) {
              setRunState((prev) =>
                prev ? { ...prev, tokens: prev.tokens + (event.total_tokens || 0) } : null
              );
            }
          } else if (event.event_type === 'approval_requested') {
            setPendingApproval(event);
          } else if (event.event_type === 'approval_resolved') {
            setPendingApproval(null);
          } else if (event.event_type === 'error') {
            if (event.message.includes('Loop') || event.message.includes('budget')) {
              setRunState((prev) => (prev ? { ...prev, status: 'failed' } : null));
            }
          }
        },
        (err) => {
          console.warn('SSE stream notice:', err);
        },
        () => {
          // Stream completed; refresh state once from API
          fetchRun(res.run_id).then(setRunState).catch(() => {});
        }
      );
    } catch (err: any) {
      setStartError(err.message || 'Failed to start run');
    } finally {
      setIsStarting(false);
    }
  };

  const handleCancelRun = async () => {
    if (!runState || isCancelling) return;
    setIsCancelling(true);
    try {
      await cancelRun(runState.run_id);
      setRunState((prev) => (prev ? { ...prev, status: 'cancelled' } : null));
    } catch (err) {
      console.error(err);
    } finally {
      setIsCancelling(false);
    }
  };

  const handleResolveApproval = async (
    decision: 'approved' | 'rejected' | 'edited',
    feedback?: string
  ) => {
    if (!runState) return;
    try {
      await resolveApproval(runState.run_id, decision, feedback);
      setPendingApproval(null);
    } catch (err) {
      console.error('Failed to resolve approval:', err);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col font-sans">
      <Header
        activeView={activeView}
        onNavigate={setActiveView}
        runState={runState}
        elapsedSeconds={elapsedSeconds}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeView === 'launch' && (
          <LaunchScreen
            onStart={handleStartRun}
            isStarting={isStarting}
            error={startError}
          />
        )}

        {activeView === 'run' && runState && (
          <div className="space-y-6">
            {/* Run overview bar */}
            <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-4 flex items-center justify-between flex-wrap gap-4">
              <div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 block mb-0.5">
                  Product Goal
                </span>
                <p className="text-sm font-semibold text-white">
                  "{runState.idea}"
                </p>
              </div>

              <div className="flex items-center gap-3">
                {runState.status === 'running' && (
                  <button
                    onClick={handleCancelRun}
                    disabled={isCancelling}
                    className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-rose-300 bg-rose-950/60 border border-rose-800/60 hover:bg-rose-900/40 flex items-center gap-1.5 transition-colors"
                  >
                    <Octagon className="w-3.5 h-3.5" />
                    <span>{isCancelling ? 'Cancelling...' : 'Cancel Run'}</span>
                  </button>
                )}

                <button
                  onClick={() => setActiveView('launch')}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-indigo-300 bg-indigo-950/60 border border-indigo-800/60 hover:bg-indigo-900/40 flex items-center gap-1.5 transition-colors"
                >
                  <Play className="w-3.5 h-3.5" />
                  <span>New Run</span>
                </button>
              </div>
            </div>

            {/* Pipeline graph */}
            <PipelineGraph
              currentStage={runState.current_stage as StageName}
              status={runState.status}
              debugIteration={debugIteration}
              maxIterations={4}
            />

            {/* Split Agent Panel + Event Timeline */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <AgentPanel
                currentRole={currentRole}
                messages={agentMessages}
                tools={tools}
              />
              <EventTimeline events={events} />
            </div>
          </div>
        )}
      </main>

      {/* Human-in-the-loop approval modal */}
      {pendingApproval && (
        <ApprovalModal
          request={pendingApproval}
          onResolve={handleResolveApproval}
          isResolving={false}
        />
      )}
    </div>
  );
};
