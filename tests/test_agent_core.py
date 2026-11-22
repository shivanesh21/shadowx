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
