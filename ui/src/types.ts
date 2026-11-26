/**
 * types.ts — Strongly-typed models matching backend schemas and events.
 */

export type StageName =
  | 'IDLE'
  | 'ANALYSIS'
  | 'DESIGN'
  | 'CODING'
  | 'TESTING'
  | 'DEBUGGING'
  | 'REVIEW'
  | 'DOCS'
  | 'DONE'
  | 'FAILED'
  | 'CANCELLED';

export type StageStatus = 'idle' | 'running' | 'done' | 'failed' | 'waiting_approval';

export interface StageInfo {
  name: StageName;
  label: string;
  role: string;
  status: StageStatus;
  startedAt?: number;
  duration?: number;
}

export interface RunState {
  run_id: string;
  idea: string;
  current_stage: StageName;
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled';
  tokens: number;
  created_at: number;
  updated_at: number;
  artifacts?: Record<string, string>;
  checkpoints?: Record<string, string>;
  history?: Array<{
    from: string;
    to: string;
    timestamp: number;
    details?: Record<string, unknown>;
  }>;
}

export type EventType =
  | 'run_started'
  | 'stage_started'
  | 'stage_finished'
  | 'run_finished'
  | 'llm_call'
  | 'agent_message'
  | 'tool_call'
  | 'tool_result'
  | 'file_changed'
  | 'test_result'
  | 'approval_requested'
  | 'approval_resolved'
  | 'loop_detected'
  | 'error';

export interface BaseEvent {
  event_type: EventType;
  run_id: string;
  event_id?: string;
  timestamp?: number;
}

export interface RunStartedEvent extends BaseEvent {
  event_type: 'run_started';
  idea: string;
}

export interface StageStartedEvent extends BaseEvent {
  event_type: 'stage_started';
  stage: StageName;
  agent_name: string;
}

export interface StageFinishedEvent extends BaseEvent {
  event_type: 'stage_finished';
  stage: StageName;
  artifacts?: Record<string, string>;
}

export interface RunFinishedEvent extends BaseEvent {
  event_type: 'run_finished';
  status: string;
  total_tokens?: number;
}

export interface LLMCallEvent extends BaseEvent {
  event_type: 'llm_call';
  model?: string;
  prompt_tokens?: number;
  response_tokens?: number;
  total_tokens?: number;
  latency_ms?: number;
}

export interface AgentMessageEvent extends BaseEvent {
  event_type: 'agent_message';
  agent_name: string;
  content: string;
}

export interface ToolCallEvent extends BaseEvent {
  event_type: 'tool_call';
  tool_name: string;
  arguments: Record<string, unknown>;
  agent_name?: string;
}

export interface ToolResultEvent extends BaseEvent {
  event_type: 'tool_result';
  tool_name: string;
  result: unknown;
  duration_ms?: number;
  error?: string;
}

export interface FileChangedEvent extends BaseEvent {
  event_type: 'file_changed';
  path: string;
  diff?: string;
  agent_name?: string;
}

export interface TestResultDataEvent extends BaseEvent {
  event_type: 'test_result';
  passed: number;
  failed: number;
  errors?: number;
  failures?: Record<string, string>;
}

export interface ApprovalRequestedEvent extends BaseEvent {
  event_type: 'approval_requested';
  stage: string;
  artifact_name: string;
  preview: string;
}

export interface ApprovalResolvedEvent extends BaseEvent {
  event_type: 'approval_resolved';
  decision: 'approved' | 'rejected' | 'edited';
  feedback?: string;
}

export interface LoopDetectedEvent extends BaseEvent {
  event_type: 'loop_detected';
  tool_name: string;
  count: number;
}

export interface ErrorEventData extends BaseEvent {
  event_type: 'error';
  message: string;
}

export type FactoryEvent =
  | RunStartedEvent
  | StageStartedEvent
  | StageFinishedEvent
  | RunFinishedEvent
  | LLMCallEvent
  | AgentMessageEvent
  | ToolCallEvent
  | ToolResultEvent
  | FileChangedEvent
  | TestResultDataEvent
  | ApprovalRequestedEvent
  | ApprovalResolvedEvent
  | LoopDetectedEvent
  | ErrorEventData;

export interface StartRunParams {
  idea: string;
  gates?: boolean;
  max_tokens?: number;
  max_time?: number;
  use_fake?: boolean;
  run_id?: string;
}
