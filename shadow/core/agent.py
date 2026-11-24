"""
agent.py — Configurable, spec-driven Agent class for ShadowX Factory.

Implements the ReAct loop, context budget management, thought_signature
preservation, event emission, and the mandatory finish() tool contract.
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from shadow.core.events import (
    Event,
    AgentMessage,
    ToolCallEvent,
    ToolResultEvent,
    LLMCallEvent,
    LoopDetected,
)
from shadow.core.event_bus import EventBus
from shadow.core.llm import LLMProvider, LLMResponse, FunctionCallData

logger = logging.getLogger(__name__)

# Finish tool declaration required for pipeline agent handoffs
FINISH_TOOL_DECLARATION = {
    "name": "finish",
    "description": "Signal that the assigned mission is complete and provide output artifacts and summary.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Concise summary of work performed and results.",
            },
            "artifacts": {
                "type": "object",
                "description": "Key-value map of created artifact names to their file paths or descriptions.",
            },
        },
        "required": ["summary"],
    },
}


@dataclass
class AgentSpec:
    """Specification defining an agent's role, constraints, and capabilities."""
    name: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    max_steps: int = 15
    model_override: Optional[str] = None
    temperature: float = 0.2
    token_budget: int = 40000
    require_finish_tool: bool = False


@dataclass
class AgentResult:
    """Outcome of an agent execution."""
    agent_name: str
    summary: str
    artifacts: dict[str, str] = field(default_factory=dict)
    steps_taken: int = 0
    total_tokens: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    finished_via_tool: bool = False


class Agent:
    """
    Reusable autonomous agent configured by an AgentSpec.
    Executes a multi-turn ReAct loop, interacts with tools, and publishes events.
    """

    def __init__(
        self,
        spec: AgentSpec,
        llm: LLMProvider,
        tool_registry: dict[str, Callable[..., Any]],
        tool_declarations: list[dict[str, Any]],
        event_bus: Optional[EventBus] = None,
        run_id: str = "default",
    ) -> None:
        self.spec = spec
        self.llm = llm
        self.tool_registry = tool_registry
        self.tool_declarations = tool_declarations
        self.event_bus = event_bus or EventBus()
        self.run_id = run_id

        # State tracking
        self.is_finished = False
        self.finish_summary: str = ""
        self.finish_artifacts: dict[str, str] = {}
        self.total_tokens: int = 0

    def _build_tools_for_role(self) -> tuple[list[dict[str, Any]], dict[str, Callable[..., Any]]]:
        """Filter available tools to only those allowed by the AgentSpec."""
        active_decls: list[dict[str, Any]] = []
        active_map: dict[str, Callable[..., Any]] = {}

        allowed = set(self.spec.allowed_tools)

        for d in self.tool_declarations:
            if not allowed or d["name"] in allowed:
                active_decls.append(d)
                if d["name"] in self.tool_registry:
                    active_map[d["name"]] = self.tool_registry[d["name"]]

        # Add mandatory finish tool if enabled
        if self.spec.require_finish_tool:
            active_decls.append(FINISH_TOOL_DECLARATION)
            active_map["finish"] = self._handle_finish

        return active_decls, active_map

    def _handle_finish(self, summary: str, artifacts: Optional[dict[str, Any]] = None, **kwargs) -> str:
        """Internal handler for finish tool call."""
        self.is_finished = True
        self.finish_summary = summary
        self.finish_artifacts = {str(k): str(v) for k, v in (artifacts or {}).items()}
        return f"OK: Mission finished. Summary: {summary}"

    def _convert_declarations_to_sdk(self, decls: list[dict[str, Any]]) -> list[Any]:
        """Convert plain dictionary declarations into SDK Tool objects if using GeminiProvider."""
        try:
            from google.genai import types
            fn_decls = []
            for d in decls:
                props = {}
                for pname, pdef in d["parameters"]["properties"].items():
                    props[pname] = types.Schema(
                        type=types.Type.STRING if pdef.get("type") == "string" else types.Type.OBJECT,
                        description=pdef.get("description", ""),
                    )
                schema = types.Schema(
                    type=types.Type.OBJECT,
                    properties=props,
                    required=d["parameters"].get("required", []),
                )
                fn_decls.append(
                    types.FunctionDeclaration(
                        name=d["name"],
                        description=d["description"],
                        parameters=schema,
                    )
                )
            return [types.Tool(function_declarations=fn_decls)]
        except ImportError:
            return decls

    def execute(
        self,
        task: str,
        initial_history: Optional[list[dict[str, Any]]] = None,
        context_files: Optional[dict[str, str]] = None,
    ) -> AgentResult:
        """
        Run the agent to complete the specified task.
        """
        active_decls, active_tools = self._build_tools_for_role()
        sdk_tools = self._convert_declarations_to_sdk(active_decls)

        # Reset per-execution finish state
        self.is_finished = False
        self.finish_summary = ""
        self.finish_artifacts = {}

        # Context setup
        user_prompt = task
        if context_files:
            file_context_str = "\n\n".join(
                f"=== {filename} ===\n{content}" for filename, content in context_files.items()
            )
            user_prompt = f"{user_prompt}\n\nProject Context:\n{file_context_str}"

        # Dual-track memory:
        # 1. live_contents: passed directly to LLMProvider (retains SDK Content & thought_signature)
        # 2. history: sanitized JSON-serializable list
        history: list[dict[str, Any]] = list(initial_history or [])
        live_contents: list[Any] = []

        # Reconstruct live_contents from initial_history
        for msg in history:
            try:
                from google.genai import types
                parts = []
                for p in msg.get("parts", []):
                    if "text" in p:
                        parts.append(types.Part(text=p["text"]))
                    elif "function_call" in p:
                        fc = p["function_call"]
                        parts.append(types.Part(function_call=types.FunctionCall(name=fc["name"], args=fc["args"])))
                    elif "function_response" in p:
                        fr = p["function_response"]
                        parts.append(types.Part(function_response=types.FunctionResponse(name=fr["name"], response={"result": fr["response"]})))
                live_contents.append(types.Content(role=msg["role"], parts=parts))
            except Exception:
                live_contents.append(msg)

        # Append new user message
        try:
            from google.genai import types
            live_contents.append(types.Content(role="user", parts=[types.Part(text=user_prompt)]))
        except Exception:
            live_contents.append({"role": "user", "parts": [{"text": user_prompt}]})

        history.append({"role": "user", "parts": [{"text": user_prompt}]})

        steps_taken = 0
        final_text_response = ""
        recent_tool_calls: list[tuple[str, str]] = []

        while steps_taken < self.spec.max_steps and not self.is_finished:
            steps_taken += 1

            # 1. Generate response from LLM
            llm_response: LLMResponse = self.llm.generate(
                contents=live_contents,
                tools=sdk_tools,
                system_instruction=self.spec.system_prompt,
                temperature=self.spec.temperature,
                model=self.spec.model_override,
            )

            self.total_tokens += llm_response.token_usage.total_tokens
            self.event_bus.emit(
                LLMCallEvent(
                    run_id=self.run_id,
                    model=self.spec.model_override or getattr(self.llm, "default_model", "mock"),
                    prompt_tokens=llm_response.token_usage.prompt_tokens,
                    completion_tokens=llm_response.token_usage.completion_tokens,
                    total_tokens=llm_response.token_usage.total_tokens,
                    latency_ms=llm_response.latency_ms,
                )
            )

            # 2. Process model output
            if llm_response.text:
                final_text_response = llm_response.text
                self.event_bus.emit(
                    AgentMessage(
                        run_id=self.run_id,
                        agent_name=self.spec.name,
                        content=llm_response.text,
                    )
                )

            # Record model turn in dual state
            if llm_response.raw_content is not None:
                live_contents.append(llm_response.raw_content)
            else:
                parts_dict: list[dict[str, Any]] = []
                if llm_response.text:
                    parts_dict.append({"text": llm_response.text})
                for fc in llm_response.function_calls:
                    parts_dict.append({"function_call": {"name": fc.name, "args": fc.args}})
                live_contents.append({"role": "model", "parts": parts_dict})

            plain_model_turn: dict[str, Any] = {"role": "model", "parts": []}
            if llm_response.text:
                plain_model_turn["parts"].append({"text": llm_response.text})
            for fc in llm_response.function_calls:
                plain_model_turn["parts"].append({"function_call": {"name": fc.name, "args": fc.args}})
            history.append(plain_model_turn)

            # If no function calls, agent has concluded its reasoning
            if not llm_response.function_calls:
                break

            # 3. Execute tool calls
            tool_resp_sdk: list[Any] = []
            tool_resp_plain: list[dict[str, Any]] = []

            for fc in llm_response.function_calls:
                tool_name = fc.name
                tool_args = fc.args

                self.event_bus.emit(
                    ToolCallEvent(
                        run_id=self.run_id,
                        agent_name=self.spec.name,
                        tool_name=tool_name,
                        arguments=tool_args,
                    )
                )

                try:
                    arg_str = json.dumps(tool_args, sort_keys=True)
                except Exception:
                    arg_str = str(tool_args)
                call_sig = (tool_name, arg_str)
                recent_tool_calls.append(call_sig)

                # Permission & loop checks
                if len(recent_tool_calls) >= 3 and recent_tool_calls[-1] == recent_tool_calls[-2] == recent_tool_calls[-3]:
                    self.event_bus.emit(
                        LoopDetected(
                            run_id=self.run_id,
                            iteration=steps_taken,
                            reason=f"Agent repeated tool '{tool_name}' 3 times with identical arguments",
                        )
                    )
                    result_str = (
                        f"LOOP DETECTED: You have invoked tool '{tool_name}' 3 times in a row with identical arguments. "
                        f"Execution blocked for this tool call. Please change your strategy."
                    )
                    is_err = True
                elif tool_name not in active_tools:
                    result_str = f"ERROR: Tool '{tool_name}' is not permitted for role '{self.spec.name}'."
                    is_err = True
                else:
                    try:
                        tool_fn = active_tools[tool_name]
                        raw_result = tool_fn(**tool_args)
                        result_str = str(raw_result)
                        is_err = "ERROR" in result_str or "BLOCKED" in result_str
                    except Exception as e:
                        result_str = f"ERROR executing {tool_name}: {e}"
                        is_err = True

                self.event_bus.emit(
                    ToolResultEvent(
                        run_id=self.run_id,
                        agent_name=self.spec.name,
                        tool_name=tool_name,
                        result=result_str,
                        is_error=is_err,
                    )
                )

                # Prepare SDK Part
                try:
                    from google.genai import types
                    tool_resp_sdk.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=tool_name,
                                response={"result": result_str},
                            )
                        )
                    )
                except Exception:
                    tool_resp_sdk.append({"name": tool_name, "response": result_str})

                tool_resp_plain.append({"function_response": {"name": tool_name, "response": result_str}})

            # Append tool responses to dual state
            try:
                from google.genai import types
                live_contents.append(types.Content(role="user", parts=tool_resp_sdk))
            except Exception:
                live_contents.append({"role": "user", "parts": tool_resp_sdk})

            history.append({"role": "user", "parts": tool_resp_plain})

            if self.is_finished:
                break

        summary = self.finish_summary or final_text_response or "Task complete."
        return AgentResult(
            agent_name=self.spec.name,
            summary=summary,
            artifacts=self.finish_artifacts,
            steps_taken=steps_taken,
            total_tokens=self.total_tokens,
            history=history,
            finished_via_tool=self.is_finished,
        )
