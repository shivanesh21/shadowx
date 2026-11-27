"""
test_agent_core.py — Unit tests for the Reusable Agent class & AgentSpec.
"""

from shadow.core.agent import Agent, AgentSpec, AgentResult
from shadow.core.llm import FakeLLMProvider, LLMResponse, FunctionCallData
from shadow.core.event_bus import EventBus


def test_agent_react_loop_with_fake_llm():
    # Mock tools
    storage = {}

    def mock_write(path: str, content: str) -> str:
        storage[path] = content
        return f"Wrote {len(content)} chars"

    tool_registry = {"write_file": mock_write}
    tool_decls = [
        {
            "name": "write_file",
            "description": "Write a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        }
    ]

    # Queue step 1: function call; step 2: final answer
    provider = FakeLLMProvider()
    provider.queue_response(
        LLMResponse(
            text="Writing the file now",
            function_calls=[FunctionCallData(name="write_file", args={"path": "output.txt", "content": "hello agent"})],
        )
    )
    provider.queue_response(
        LLMResponse(text="File written successfully. Done.")
    )

    spec = AgentSpec(name="TesterAgent", system_prompt="You are a test agent.", allowed_tools=["write_file"])
    bus = EventBus()

    agent = Agent(spec=spec, llm=provider, tool_registry=tool_registry, tool_declarations=tool_decls, event_bus=bus)
    result: AgentResult = agent.execute(task="Write output.txt")

    assert result.agent_name == "TesterAgent"
    assert result.steps_taken == 2
    assert "output.txt" in storage
    assert storage["output.txt"] == "hello agent"
    assert "Done." in result.summary


def test_agent_role_tool_permissions():
    """Verify an agent cannot execute tools not permitted in its AgentSpec."""
    tool_registry = {"dangerous_tool": lambda: "boom"}
    tool_decls = [{"name": "dangerous_tool", "description": "dangerous", "parameters": {"type": "object", "properties": {}}}]

    provider = FakeLLMProvider()
    # Model attempts to call dangerous_tool
    provider.queue_response(
        LLMResponse(function_calls=[FunctionCallData(name="dangerous_tool", args={})])
    )
    provider.queue_response(LLMResponse(text="I understand the permission error."))

    spec = AgentSpec(name="RestrictedRole", system_prompt="Safe role", allowed_tools=["safe_tool_only"])
    bus = EventBus()

    agent = Agent(spec=spec, llm=provider, tool_registry=tool_registry, tool_declarations=tool_decls, event_bus=bus)
    result = agent.execute(task="Do something dangerous")

    # Inspect events to verify tool was blocked with permission error
    tool_results = [e for e in bus.history if e.event_type == "tool_result"]
    assert len(tool_results) == 1
    assert "not permitted for role" in tool_results[0].result


def test_agent_finish_tool():
    """Verify that calling finish() tool records summary and artifacts and halts the loop."""
    provider = FakeLLMProvider()
    provider.queue_response(
        LLMResponse(
            function_calls=[
                FunctionCallData(
                    name="finish",
                    args={
                        "summary": "Completed requirements definition",
                        "artifacts": {"requirements": "docs/requirements.md"},
                    },
                )
            ]
        )
    )

    spec = AgentSpec(
        name="Analyst",
        system_prompt="You are an analyst.",
        allowed_tools=[],
        require_finish_tool=True,
    )
    agent = Agent(spec=spec, llm=provider, tool_registry={}, tool_declarations=[])
    result = agent.execute(task="Analyze this project")

    assert result.finished_via_tool is True
    assert result.summary == "Completed requirements definition"
    assert result.artifacts == {"requirements": "docs/requirements.md"}
    assert result.steps_taken == 1


def test_estimate_tokens():
    from shadow.core.agent import estimate_tokens
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello world") >= 2
    # 400 characters is ~100 tokens
    assert 90 <= estimate_tokens("a" * 400) <= 110


def test_context_trimming_preserves_thought_signatures():
    from shadow.core.agent import Agent, AgentSpec

    spec = AgentSpec(name="TestTrimmer", system_prompt="System", token_budget=1000)
    agent = Agent(spec=spec, llm=FakeLLMProvider(), tool_registry={}, tool_declarations=[])

    # Giant output to simulate huge tool result exceeding budget threshold
    huge_output = "Line " + ("X" * 100 + "\n") * 60  # > 6000 chars

    # Dummy native-like object to verify model turns aren't touched
    class MockModelTurn:
        thought_signature = b"valid_gemini_thought_sig"
        text = "Thinking..."

    model_turn = MockModelTurn()

    live_contents = [
        {"role": "user", "parts": [{"text": "Do task"}]},
        {"role": "model", "parts": [model_turn]},
        {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "name": "run_command",
                        "response": {"result": huge_output},
                    }
                }
            ],
        },
    ]

    history = [
        {"role": "user", "parts": [{"text": "Do task"}]},
        {"role": "model", "thought": "Thinking...", "parts": []},
        {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "name": "run_command",
                        "response": huge_output,
                    }
                }
            ],
        },
    ]

    agent._trim_context(live_contents, history)

    # 1. Model turn must remain completely intact (object identity & thought_signature untouched)
    assert live_contents[1]["parts"][0] is model_turn
    assert live_contents[1]["parts"][0].thought_signature == b"valid_gemini_thought_sig"

    # 2. Tool response in live_contents must be trimmed
    trimmed_result = live_contents[2]["parts"][0]["function_response"]["response"]["result"]
    assert "[Output trimmed" in trimmed_result
    assert len(trimmed_result) < len(huge_output)

    # 3. History entry must also be trimmed
    trimmed_hist = history[2]["parts"][0]["function_response"]["response"]
    assert "[Output trimmed" in trimmed_hist
    assert len(trimmed_hist) < len(huge_output)


def test_agent_accumulates_cost():
    from shadow.core.llm import TokenUsage

    provider = FakeLLMProvider()
    provider.queue_response(LLMResponse(
        text="Step 1 completed",
        token_usage=TokenUsage(prompt_tokens=2000, completion_tokens=500, total_tokens=2500),
    ))
    provider.queue_response(LLMResponse(
        text="Final answer",
        token_usage=TokenUsage(prompt_tokens=2500, completion_tokens=200, total_tokens=2700),
    ))

    spec = AgentSpec(name="CostAgent", system_prompt="Track cost", allowed_tools=[])
    agent = Agent(spec=spec, llm=provider, tool_registry={}, tool_declarations=[])
    result = agent.execute("Compute something")

    assert result.total_cost_usd > 0
    assert abs(result.total_cost_usd - (agent.total_cost_usd)) < 1e-9
