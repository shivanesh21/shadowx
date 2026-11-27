"""
events.py — Strongly-typed event dataclasses for ShadowX Factory.

Every agent action, LLM call, state machine transition, and tool execution
emits a typed event. This decouples business logic from rendering (CLI and Web UI).
"""

from __future__ import annotations
import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Event:
    """Base event model with timestamp and unique ID."""
    event_type: str
    run_id: str = "default"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class RunStarted(Event):
    idea: str = ""
    event_type: str = "run_started"


@dataclass
class StageStarted(Event):
    stage: str = ""
    agent_name: str = ""
    event_type: str = "stage_started"


@dataclass
class LLMCallEvent(Event):
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    event_type: str = "llm_call"


@dataclass
class AgentMessage(Event):
    agent_name: str = ""
    content: str = ""
    event_type: str = "agent_message"


@dataclass
class ToolCallEvent(Event):
    agent_name: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    event_type: str = "tool_call"


@dataclass
class ToolResultEvent(Event):
    agent_name: str = ""
    tool_name: str = ""
    result: str = ""
    is_error: bool = False
    event_type: str = "tool_result"


@dataclass
class FileChanged(Event):
    path: str = ""
    diff: str = ""
    agent_name: str = ""
    event_type: str = "file_changed"


@dataclass
class ArtifactCreated(Event):
    name: str = ""
    path: str = ""
    artifact_type: str = ""
    event_type: str = "artifact_created"


@dataclass
class TestResultEvent(Event):
    __test__ = False  # Prevent pytest from collecting this dataclass as a test suite
    passed: int = 0
    failed: int = 0
    errors: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    event_type: str = "test_result"


@dataclass
class ApprovalRequested(Event):
    stage: str = ""
    artifact_name: str = ""
    preview: str = ""
    event_type: str = "approval_requested"


@dataclass
class ApprovalResolved(Event):
    decision: str = ""  # approved | rejected | edited
    feedback: str = ""
    event_type: str = "approval_resolved"


@dataclass
class LoopDetected(Event):
    iteration: int = 0
    failure_hash: str = ""
    reason: str = ""
    event_type: str = "loop_detected"


@dataclass
class StageFinished(Event):
    stage: str = ""
    summary: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    event_type: str = "stage_finished"


@dataclass
class RunFinished(Event):
    status: str = "success"  # success | failed | cancelled
    duration_s: float = 0.0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    event_type: str = "run_finished"


@dataclass
class ErrorEvent(Event):
    message: str = ""
    details: str = ""
    event_type: str = "error"
