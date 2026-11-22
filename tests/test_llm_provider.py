"""
test_llm_provider.py — Unit tests for LLMProvider implementations.
"""

import pytest
from shadow.core.llm import (
    FakeLLMProvider,
    LLMResponse,
    FunctionCallData,
    TokenUsage,
)


def test_fake_llm_provider_queued_response():
    provider = FakeLLMProvider()
    provider.queue_response(LLMResponse(
        text="Plan: Create file",
        function_calls=[FunctionCallData(name="write_file", args={"path": "test.txt", "content": "hi"})],
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=15, total_tokens=25),
        latency_ms=120.0,
    ))
    provider.queue_response(LLMResponse(text="Task is finished!"))

    resp1 = provider.generate(contents=[{"role": "user", "parts": [{"text": "create test.txt"}]}])
    assert resp1.text == "Plan: Create file"
    assert len(resp1.function_calls) == 1
    assert resp1.function_calls[0].name == "write_file"
    assert resp1.token_usage.total_tokens == 25

    resp2 = provider.generate(contents=[])
    assert resp2.text == "Task is finished!"
    assert len(resp2.function_calls) == 0

    assert len(provider.call_history) == 2


def test_fake_llm_provider_simulated_exception():
    provider = FakeLLMProvider()
    provider.queue_response(RuntimeError("Simulated LLM rate limit"))

    with pytest.raises(RuntimeError, match="Simulated LLM rate limit"):
        provider.generate(contents=[])
