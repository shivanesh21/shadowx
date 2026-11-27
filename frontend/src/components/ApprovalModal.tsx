import React, { useState } from 'react';
import { ShieldAlert, Check, X, Edit3 } from 'lucide-react';
import { ApprovalRequestedEvent } from '../types';

interface ApprovalModalProps {
  request: ApprovalRequestedEvent;
  onResolve: (decision: 'approved' | 'rejected' | 'edited', feedback?: string) => void;
  isResolving: boolean;
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  request,
  onResolve,
  isResolving,
}) => {
  const [feedback, setFeedback] = useState('');
  const [mode, setMode] = useState<'decision' | 'feedback' | 'edit'>('decision');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="max-w-2xl w-full bg-gray-900 border border-amber-600/60 rounded-xl p-6 shadow-2xl shadow-amber-950/30">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-amber-950/80 border border-amber-600/50 flex items-center justify-center text-amber-400">
            <ShieldAlert className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-amber-400">
              Human-in-the-Loop Approval Required
            </div>
            <h3 className="text-lg font-bold text-white">
              Stage: {request.stage}
            </h3>
          </div>
        </div>

        <div className="mb-4">
          <div className="text-xs text-gray-400 mb-1">
            Deliverable Artifact: <span className="font-mono text-gray-200">{request.artifact_name}</span>
          </div>
          <div className="bg-gray-950 border border-gray-800 rounded-lg p-3 max-h-56 overflow-y-auto font-mono text-xs text-gray-300 whitespace-pre-wrap">
            {request.preview || 'No preview available.'}
          </div>
        </div>

        {mode === 'feedback' && (
          <div className="mb-4">
            <label className="block text-xs font-semibold text-rose-300 mb-1">
              Rejection Feedback for Agent:
            </label>
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Explain why this deliverable was rejected and what needs to change..."
              rows={3}
              className="w-full bg-gray-950 border border-gray-800 rounded-lg p-2.5 text-xs text-gray-200 focus:outline-none focus:border-rose-500 font-mono"
            />
          </div>
        )}

        {mode === 'edit' && (
          <div className="mb-4">
            <label className="block text-xs font-semibold text-indigo-300 mb-1">
              Edit Notes / Clarifications:
            </label>
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Enter edits or notes for the agent to incorporate..."
              rows={3}
              className="w-full bg-gray-950 border border-gray-800 rounded-lg p-2.5 text-xs text-gray-200 focus:outline-none focus:border-indigo-500 font-mono"
            />
          </div>
        )}

        <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-gray-800">
          {mode === 'decision' ? (
            <>
              <button
                type="button"
                disabled={isResolving}
                onClick={() => setMode('feedback')}
                className="px-4 py-2 rounded-lg text-xs font-semibold text-rose-400 bg-rose-950/60 border border-rose-800/60 hover:bg-rose-900/40 flex items-center gap-1.5"
              >
                <X className="w-3.5 h-3.5" /> Reject with Feedback
              </button>
              <button
                type="button"
                disabled={isResolving}
                onClick={() => setMode('edit')}
                className="px-4 py-2 rounded-lg text-xs font-semibold text-indigo-400 bg-indigo-950/60 border border-indigo-800/60 hover:bg-indigo-900/40 flex items-center gap-1.5"
              >
                <Edit3 className="w-3.5 h-3.5" /> Edit / Add Notes
              </button>
              <button
                type="button"
                disabled={isResolving}
                onClick={() => onResolve('approved')}
                className="px-5 py-2 rounded-lg text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 flex items-center gap-1.5 shadow-lg shadow-emerald-600/20"
              >
                <Check className="w-3.5 h-3.5" /> Approve & Continue
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setMode('decision')}
                className="px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-white"
              >
                Back
              </button>
              <button
                type="button"
                disabled={isResolving || (mode === 'feedback' && !feedback.trim())}
                onClick={() => onResolve(mode === 'feedback' ? 'rejected' : 'edited', feedback)}
                className="px-5 py-2 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500"
              >
                Confirm {mode === 'feedback' ? 'Rejection' : 'Edits'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
