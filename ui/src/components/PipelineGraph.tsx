import React from 'react';
import {
  FileText,
  Compass,
  Code2,
  CheckCircle2,
  Bug,
  ShieldCheck,
  BookOpen,
  Sparkles,
  ArrowRight,
  Repeat,
  AlertCircle,
  Clock,
  Loader2,
} from 'lucide-react';
import { StageName, StageStatus } from '../types';

interface PipelineGraphProps {
  currentStage: StageName;
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled';
  debugIteration?: number;
  maxIterations?: number;
}

interface StageMeta {
  id: StageName;
  label: string;
  role: string;
  description: string;
  icon: React.ElementType;
}

const STAGES: StageMeta[] = [
  {
    id: 'ANALYSIS',
    label: 'Requirements',
    role: 'Analyst',
    description: 'User stories, acceptance criteria & scope',
    icon: FileText,
  },
  {
    id: 'DESIGN',
    label: 'Architecture',
    role: 'Architect',
    description: 'System design, module specs & Mermaid',
    icon: Compass,
  },
  {
    id: 'CODING',
    label: 'Implementation',
    role: 'Developer',
    description: 'Source code in isolated workspace',
    icon: Code2,
  },
  {
    id: 'TESTING',
    label: 'Verification',
    role: 'Tester',
    description: 'Acceptance tests derived from AC',
    icon: CheckCircle2,
  },
  {
    id: 'DEBUGGING',
    label: 'Root Cause Fix',
    role: 'Debugger',
    description: 'Minimal surgical fixes to src/',
    icon: Bug,
  },
  {
    id: 'REVIEW',
    label: 'Quality & Trace',
    role: 'Reviewer',
    description: 'Security & traceability matrix',
    icon: ShieldCheck,
  },
  {
    id: 'DOCS',
    label: 'Documentation',
    role: 'Documenter',
    description: 'Verified README & changelog',
    icon: BookOpen,
  },
];

const STAGE_ORDER: StageName[] = [
  'ANALYSIS',
  'DESIGN',
  'CODING',
  'TESTING',
  'DEBUGGING',
  'REVIEW',
  'DOCS',
];

export const PipelineGraph: React.FC<PipelineGraphProps> = ({
  currentStage,
  status,
  debugIteration = 0,
  maxIterations = 4,
}) => {
  const getStageStatus = (stageId: StageName): StageStatus => {
    if (status === 'failed' && currentStage === stageId) return 'failed';
    if (status === 'done') return 'done';

    const currentIndex = STAGE_ORDER.indexOf(currentStage);
    const stageIndex = STAGE_ORDER.indexOf(stageId);

    if (stageIndex === -1 || currentIndex === -1) return 'idle';

    if (stageIndex < currentIndex) {
      return 'done';
    }
    if (stageIndex === currentIndex) {
      return status === 'running' ? 'running' : 'idle';
    }
    return 'idle';
  };

  return (
    <div className="w-full bg-gray-900/90 border border-gray-800 rounded-xl p-5 shadow-xl backdrop-blur-sm">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-gray-200 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-400" />
            Autonomous SDLC Pipeline Graph
          </h2>
          <p className="text-xs text-gray-400">
            Deterministic state machine with automated git checkpoints per stage
          </p>
        </div>

        {/* Debug iteration counter badge */}
        {(currentStage === 'TESTING' || currentStage === 'DEBUGGING' || debugIteration > 0) && (
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-950/70 border border-indigo-700/50 text-indigo-300 text-xs font-mono">
            <Repeat className="w-3.5 h-3.5 text-indigo-400 animate-spin-slow" />
            <span>Tester ↔ Debugger Loop: {debugIteration}/{maxIterations}</span>
          </div>
        )}
      </div>

      {/* Horizontal Graph layout */}
      <div className="overflow-x-auto pb-2">
        <div className="min-w-[900px] flex items-center justify-between gap-1 py-3 px-2">
          {STAGES.map((stage, idx) => {
            const Icon = stage.icon;
            const stageStatus = getStageStatus(stage.id);
            const isLast = idx === STAGES.length - 1;
            const isTesterDebuggerBridge = stage.id === 'TESTING';

            let borderClass = 'border-gray-800 bg-gray-950/60 text-gray-400';
            let iconClass = 'text-gray-500 bg-gray-900';

            if (stageStatus === 'running') {
              borderClass = 'border-indigo-500 bg-indigo-950/30 text-indigo-200 shadow-lg shadow-indigo-500/20 ring-1 ring-indigo-500 animate-pulse-fast';
              iconClass = 'text-indigo-400 bg-indigo-900/50';
            } else if (stageStatus === 'done') {
              borderClass = 'border-emerald-700/60 bg-emerald-950/20 text-gray-200';
              iconClass = 'text-emerald-400 bg-emerald-950/50';
            } else if (stageStatus === 'failed') {
              borderClass = 'border-rose-600 bg-rose-950/30 text-rose-200 shadow-lg shadow-rose-500/20';
              iconClass = 'text-rose-400 bg-rose-950/50';
            }

            return (
              <React.Fragment key={stage.id}>
                {/* Stage Node */}
                <div
                  className={`flex-1 min-w-[110px] max-w-[130px] rounded-lg border p-2.5 transition-all relative ${borderClass}`}
                >
                  {/* Status indicator badge */}
                  <div className="flex items-center justify-between mb-1.5">
                    <div className={`w-7 h-7 rounded-md flex items-center justify-center ${iconClass}`}>
                      {stageStatus === 'running' ? (
                        <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                      ) : (
                        <Icon className="w-4 h-4" />
                      )}
                    </div>
                    {stageStatus === 'done' && (
                      <span className="w-4 h-4 rounded-full bg-emerald-900/80 text-emerald-400 flex items-center justify-center text-[10px]">
                        ✓
                      </span>
                    )}
                    {stageStatus === 'failed' && (
                      <AlertCircle className="w-4 h-4 text-rose-400" />
                    )}
                    {stageStatus === 'idle' && (
                      <Clock className="w-3 h-3 text-gray-600" />
                    )}
                  </div>

                  <div className="text-[11px] font-bold tracking-tight text-white truncate">
                    {stage.label}
                  </div>
                  <div className="text-[10px] font-medium text-indigo-400 uppercase tracking-wider mb-1">
                    {stage.role}
                  </div>
                  <div className="text-[9px] text-gray-400 leading-tight line-clamp-2">
                    {stage.description}
                  </div>
                </div>

                {/* Connector arrow between stages */}
                {!isLast && (
                  <div className="flex items-center px-1 text-gray-600">
                    {isTesterDebuggerBridge ? (
                      <div className="flex flex-col items-center">
                        <ArrowRight className="w-4 h-4 text-indigo-400" />
                        <span className="text-[9px] text-indigo-400 font-mono">↻</span>
                      </div>
                    ) : (
                      <ArrowRight className="w-4 h-4 text-gray-700" />
                    )}
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
};
