"""
shadow.core — Core engine for ShadowX Factory.

Exports:
  - Agent, AgentSpec, AgentResult
  - EventBus, Event and typed event subclasses
  - LLMProvider, GeminiProvider, FakeLLMProvider, LLMResponse
"""

from shadow.core.events import (
    Event,
    RunStarted,
    StageStarted,
    LLMCallEvent,
    AgentMessage,
    ToolCallEvent,
    ToolResultEvent,
    FileChanged,
    ArtifactCreated,
    TestResultEvent,
    ApprovalRequested,
    ApprovalResolved,
    LoopDetected,
    StageFinished,
    RunFinished,
    ErrorEvent,
)
from shadow.core.event_bus import EventBus
from shadow.core.llm import (
    LLMProvider,
    GeminiProvider,
    FakeLLMProvider,
    LLMResponse,
    TokenUsage,
    FunctionCallData,
)
from shadow.core.agent import Agent, AgentSpec, AgentResult

__all__ = [
    "Agent",
    "AgentSpec",
    "AgentResult",
    "EventBus",
    "Event",
    "RunStarted",
    "StageStarted",
    "LLMCallEvent",
    "AgentMessage",
    "ToolCallEvent",
    "ToolResultEvent",
    "FileChanged",
    "ArtifactCreated",
    "TestResultEvent",
    "ApprovalRequested",
    "ApprovalResolved",
    "LoopDetected",
    "StageFinished",
    "RunFinished",
    "ErrorEvent",
    "LLMProvider",
    "GeminiProvider",
    "FakeLLMProvider",
    "LLMResponse",
    "TokenUsage",
    "FunctionCallData",
]
