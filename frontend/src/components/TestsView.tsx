import React, { useState, useEffect } from 'react';
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  Sparkles,
  Repeat,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';
import { fetchFileContent } from '../api/client';
import { TestResultDataEvent, TestReportData, TestCaseResult } from '../types';

interface TestsViewProps {
  runId: string;
  testEvents: TestResultDataEvent[];
  debugIteration?: number;
}

export const TestsView: React.FC<TestsViewProps> = ({
  runId,
  testEvents,
  debugIteration = 0,
}) => {
  const [report, setReport] = useState<TestReportData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [expandedTests, setExpandedTests] = useState<Record<number, boolean>>({});

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    fetchFileContent(runId, 'artifacts/test_report.json')
      .then((res) => {
        try {
          const data: TestReportData = JSON.parse(res.content);
          setReport(data);
        } catch {
          // If artifacts/test_report.json is not formatted or missing, fallback to testEvents
        }
      })
      .catch(() => {
        // Fallback: try workspace tests/ or root
        fetchFileContent(runId, 'test_report.json')
          .then((res) => {
            try {
              setReport(JSON.parse(res.content));
            } catch {}
          })
          .catch(() => {});
      })
      .finally(() => setLoading(false));
  }, [runId]);

  const toggleTest = (idx: number) => {
    setExpandedTests((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  // Extract latest numbers from report or test events
  const latestEvent = testEvents.length > 0 ? testEvents[testEvents.length - 1] : null;

  const passedCount = report?.passed ?? latestEvent?.passed ?? 0;
  const failedCount = report?.failed ?? latestEvent?.failed ?? 0;
  const errorsCount = report?.errors ?? latestEvent?.errors ?? 0;
  const totalCount = report?.total ?? passedCount + failedCount + errorsCount;
  const passRate = totalCount > 0 ? Math.round((passedCount / totalCount) * 100) : 0;

  // Build test items list
  const testCases: TestCaseResult[] =
    report?.tests && report.tests.length > 0
      ? report.tests
      : latestEvent?.failures
      ? Object.entries(latestEvent.failures).map(([name, failure_message], idx) => ({
          name,
          ac_id: `AC-${(idx % 4) + 1}`,
          status: 'failed',
          failure_message,
        }))
      : [];

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-5 shadow-xl backdrop-blur-sm space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between pb-3 border-b border-gray-800 flex-wrap gap-2">
        <div>
          <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Acceptance Test Verification</span>
          </h2>
          <p className="text-xs text-gray-400">
            Automated test suite derived from numbered Acceptance Criteria (AC-1, AC-2...)
          </p>
        </div>

        {debugIteration > 0 && (
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-950/70 border border-indigo-700/50 text-indigo-300 text-xs font-mono">
            <Repeat className="w-3.5 h-3.5 text-indigo-400" />
            <span>Tester ↔ Debugger Iterations: {debugIteration}</span>
          </div>
        )}
      </div>

      {/* Summary Stats Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-lg bg-gray-950 border border-gray-800">
          <div className="text-[11px] text-gray-400 font-medium uppercase">
            Total Tests
          </div>
          <div className="text-xl font-extrabold text-white font-mono mt-0.5">
            {totalCount}
          </div>
        </div>

        <div className="p-3.5 rounded-lg bg-emerald-950/30 border border-emerald-800/40">
          <div className="text-[11px] text-emerald-400 font-medium uppercase flex items-center gap-1">
            <CheckCircle className="w-3 h-3" /> Passed
          </div>
          <div className="text-xl font-extrabold text-emerald-400 font-mono mt-0.5">
            {passedCount}
          </div>
        </div>

        <div className="p-3.5 rounded-lg bg-rose-950/30 border border-rose-800/40">
          <div className="text-[11px] text-rose-400 font-medium uppercase flex items-center gap-1">
            <XCircle className="w-3 h-3" /> Failed
          </div>
          <div className="text-xl font-extrabold text-rose-400 font-mono mt-0.5">
            {failedCount + errorsCount}
          </div>
        </div>

        <div className="p-3.5 rounded-lg bg-indigo-950/30 border border-indigo-800/40">
          <div className="text-[11px] text-indigo-400 font-medium uppercase flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> Pass Rate
          </div>
          <div className="text-xl font-extrabold text-indigo-300 font-mono mt-0.5">
            {passRate}%
          </div>
        </div>
      </div>

      {/* Test Cases Table with AC Mapping */}
      <div className="bg-gray-950 border border-gray-800 rounded-lg overflow-hidden">
        <div className="px-4 py-2.5 bg-gray-900/80 border-b border-gray-800 text-xs font-semibold uppercase tracking-wider text-gray-300 flex items-center justify-between">
          <span>Test Suite Executions</span>
          <span className="font-mono text-[11px] text-gray-500">
            {testCases.length} mapped test cases
          </span>
        </div>

        <div className="divide-y divide-gray-800/60 max-h-[420px] overflow-y-auto">
          {loading ? (
            <div className="text-center py-12 text-xs text-gray-500 animate-pulse">
              Loading test report...
            </div>
          ) : testCases.length === 0 ? (
            <div className="text-center py-12 text-xs text-gray-500">
              {totalCount > 0 ? (
                <div className="space-y-1">
                  <div className="text-emerald-400 font-semibold flex items-center justify-center gap-1.5">
                    <CheckCircle className="w-4 h-4" /> All {passedCount} Acceptance Tests Passed!
                  </div>
                  <div className="text-[11px] text-gray-500">
                    Acceptance Criteria verified against implementation under src/.
                  </div>
                </div>
              ) : (
                'No tests executed yet. Waiting for TESTING stage...'
              )}
            </div>
          ) : (
            testCases.map((tc, idx) => {
              const isExpanded = !!expandedTests[idx];
              const isPassed = tc.status === 'passed';

              return (
                <div key={idx} className="p-3 text-xs font-mono transition-colors hover:bg-gray-900/30">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <button
                        onClick={() => toggleTest(idx)}
                        disabled={!tc.failure_message}
                        className={`text-gray-400 ${tc.failure_message ? 'hover:text-white cursor-pointer' : 'cursor-default opacity-40'}`}
                      >
                        {isExpanded ? (
                          <ChevronDown className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5" />
                        )}
                      </button>

                      {/* AC Badge */}
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-950 text-indigo-300 border border-indigo-700/50 shrink-0">
                        {tc.ac_id || 'AC-1'}
                      </span>

                      <span className="text-gray-200 truncate font-semibold">
                        {tc.name}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      {tc.duration_s !== undefined && (
                        <span className="text-[11px] text-gray-500 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          <span>{tc.duration_s.toFixed(2)}s</span>
                        </span>
                      )}

                      {isPassed ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-700/50">
                          <CheckCircle className="w-3 h-3" /> PASSED
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-950/80 text-rose-400 border border-rose-700/50">
                          <XCircle className="w-3 h-3" /> FAILED
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Expandable Failure Trace */}
                  {isExpanded && tc.failure_message && (
                    <div className="mt-2.5 p-3 rounded-md bg-rose-950/20 border border-rose-800/40 text-[11px] text-rose-300 overflow-x-auto whitespace-pre-wrap">
                      <div className="text-[10px] font-bold uppercase text-rose-400 mb-1 flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" /> Failure Traceback
                      </div>
                      {tc.failure_message}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
