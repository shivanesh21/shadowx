/**
 * client.ts — API client and SSE stream connector for ShadowX Factory.
 */

import { FactoryEvent, RunState, StartRunParams } from '../types';

const API_BASE = ''; // Relies on Vite proxy or same-origin FastAPI serving

export async function startRun(params: StartRunParams): Promise<{ run_id: string; status: string }> {
  const resp = await fetch(`${API_BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Failed to start run' }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function fetchRuns(): Promise<RunState[]> {
  const resp = await fetch(`${API_BASE}/runs`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchRun(runId: string): Promise<RunState> {
  const resp = await fetch(`${API_BASE}/runs/${runId}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function cancelRun(runId: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/runs/${runId}/cancel`, { method: 'POST' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
}

export async function resolveApproval(
  runId: string,
  decision: 'approved' | 'rejected' | 'edited',
  feedback: string = ''
): Promise<void> {
  const resp = await fetch(`${API_BASE}/runs/${runId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, feedback }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
}

export async function fetchFiles(runId: string): Promise<string[]> {
  const resp = await fetch(`${API_BASE}/runs/${runId}/files`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchFileContent(runId: string, filePath: string): Promise<{ content: string; size_bytes: number }> {
  const resp = await fetch(`${API_BASE}/runs/${runId}/files/${encodeURIComponent(filePath).replace(/%2F/g, '/')}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchArtifacts(runId: string): Promise<{ run_id: string; artifacts: Record<string, { path: string; exists: boolean; size_bytes: number }> }> {
  const resp = await fetch(`${API_BASE}/runs/${runId}/artifacts`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export function getZipDownloadUrl(runId: string): string {
  return `${API_BASE}/runs/${runId}/zip`;
}

export async function fetchMetrics(): Promise<import('../types').MetricsResponse> {
  const resp = await fetch(`${API_BASE}/metrics/compare`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchCompare(runIds: string[]): Promise<import('../types').MetricsResponse> {
  const q = runIds.join(',');
  const resp = await fetch(`${API_BASE}/metrics/compare?run_ids=${encodeURIComponent(q)}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchPerRunMetrics(runId: string): Promise<import('../types').PerRunMetrics> {
  const resp = await fetch(`${API_BASE}/runs/${runId}/metrics`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchEvalBenchmark(): Promise<import('../types').EvalBenchmarkData> {
  const resp = await fetch(`${API_BASE}/metrics/evals`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchDemoRuns(): Promise<import('../types').DemoRun[]> {
  const resp = await fetch(`${API_BASE}/runs/demo/list`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchRawEvents(runId: string): Promise<FactoryEvent[]> {
  const resp = await fetch(`${API_BASE}/runs/${runId}/raw-events`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

/**
 * Connect to the SSE endpoint for a given run and stream events back via callback.
 */
export function subscribeToEvents(
  runId: string,
  onEvent: (event: FactoryEvent) => void,
  onError?: (err: Event) => void,
  onDone?: () => void
): () => void {
  const eventSource = new EventSource(`${API_BASE}/runs/${runId}/events`);

  eventSource.onmessage = (e) => {
    try {
      const data: FactoryEvent = JSON.parse(e.data);
      onEvent(data);
    } catch {
      // Non-json message or ping
    }
  };

  eventSource.addEventListener('done', () => {
    if (onDone) onDone();
    eventSource.close();
  });

  eventSource.onerror = (e) => {
    if (onError) onError(e);
  };

  return () => {
    eventSource.close();
  };
}
