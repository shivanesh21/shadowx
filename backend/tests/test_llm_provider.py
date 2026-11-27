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


def test_calculate_cost():
    from shadow.core.llm import calculate_cost

    # gemini-2.5-pro: $1.25 / 1M prompt, $5.00 / 1M completion
    cost_pro = calculate_cost("gemini-2.5-pro", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert abs(cost_pro - 6.25) < 1e-5

    # gemini-2.5-flash: $0.15 / 1M prompt, $0.60 / 1M completion
    cost_flash = calculate_cost("gemini-2.5-flash", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert abs(cost_flash - 0.75) < 1e-5

    # gemini-2.5-flash-lite: $0.075 / 1M prompt, $0.30 / 1M completion
    cost_lite = calculate_cost("gemini-2.5-flash-lite", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert abs(cost_lite - 0.375) < 1e-5

    # Fallback default pricing
    cost_unknown = calculate_cost("custom-model-x", prompt_tokens=1000, completion_tokens=1000)
    assert cost_unknown > 0


def test_fake_llm_provider_computes_cost():
    provider = FakeLLMProvider()
    provider.queue_response(LLMResponse(
        text="Analysis done",
        token_usage=TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
    ))
    resp = provider.generate(contents=[], model="gemini-2.5-flash")
    assert resp.cost_usd > 0
    # 1000 * 0.15/1M + 500 * 0.60/1M = 0.00015 + 0.00030 = 0.00045
    assert abs(resp.cost_usd - 0.00045) < 1e-6
