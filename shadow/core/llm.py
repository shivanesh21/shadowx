"""
llm.py — LLM Provider abstraction for ShadowX Factory.

Provides:
  - LLMProvider (Abstract Base Class)
  - LLMResponse & TokenUsage data models
  - GeminiProvider (google-genai with exponential backoff on 429/5xx and thought_signature handling)
  - FakeLLMProvider (scripted responses for 100% offline, deterministic unit tests)
"""

from __future__ import annotations
import os
import time
import random
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Model pricing table per 1,000,000 tokens (USD)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.5-pro": {"prompt_per_m": 1.25, "completion_per_m": 5.00},
    "gemini-1.5-pro": {"prompt_per_m": 1.25, "completion_per_m": 5.00},
    "gemini-2.5-flash": {"prompt_per_m": 0.15, "completion_per_m": 0.60},
    "gemini-1.5-flash": {"prompt_per_m": 0.15, "completion_per_m": 0.60},
    "gemini-2.5-flash-lite": {"prompt_per_m": 0.075, "completion_per_m": 0.30},
    "gemini-3.5-flash-lite": {"prompt_per_m": 0.075, "completion_per_m": 0.30},
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Compute estimated cost in USD based on prompt and completion token counts.
    Defaults to flash pricing tier if the model name is unknown.
    """
    matched = None
    model_lower = (model or "").lower()
    # Sort by key length descending so longer/more specific names match first (e.g. flash-lite before flash)
    for key in sorted(MODEL_PRICING.keys(), key=len, reverse=True):
        if key in model_lower:
            matched = MODEL_PRICING[key]
            break
    if not matched:
        if "pro" in model_lower:
            matched = MODEL_PRICING["gemini-2.5-pro"]
        elif "lite" in model_lower:
            matched = MODEL_PRICING["gemini-2.5-flash-lite"]
        else:
            matched = MODEL_PRICING["gemini-2.5-flash"]

    cost = (prompt_tokens / 1_000_000.0) * matched["prompt_per_m"] + (
        completion_tokens / 1_000_000.0
    ) * matched["completion_per_m"]
    return round(cost, 6)


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class FunctionCallData:
    name: str
    args: dict[str, Any]


@dataclass
class LLMResponse:
    text: Optional[str] = None
    function_calls: list[FunctionCallData] = field(default_factory=list)
    raw_content: Any = None  # Native SDK Content object (preserves thought_signature)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    cost_usd: float = 0.0


class LLMProvider(ABC):
    """Abstract interface for model inference providers."""

    @abstractmethod
    def generate(
        self,
        contents: list[Any],
        tools: Optional[list[Any]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        model: Optional[str] = None,
    ) -> LLMResponse:
        """Generate response from LLM."""
        pass


class GeminiProvider(LLMProvider):
    """
    Production Gemini provider using google-genai SDK v2.
    Implements exponential backoff on rate-limits (429) and server errors (5xx).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gemini-3.5-flash-lite",
        max_retries: int = 4,
        initial_backoff: float = 1.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")
        self.default_model = os.environ.get("MODEL_NAME", default_model)
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff

        from google import genai
        self.client = genai.Client(api_key=self.api_key)

    def generate(
        self,
        contents: list[Any],
        tools: Optional[list[Any]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        model: Optional[str] = None,
    ) -> LLMResponse:
        from google.genai import types

        target_model = model or self.default_model
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            tools=tools or None,
        )

        backoff = self.initial_backoff
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                start_time = time.perf_counter()
                response = self.client.models.generate_content(
                    model=target_model,
                    contents=contents,
                    config=config,
                )
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                candidate = response.candidates[0] if response.candidates else None
                if not candidate or not candidate.content:
                    return LLMResponse(
                        text="",
                        raw_content=getattr(candidate, "content", None),
                        latency_ms=latency_ms,
                    )

                raw_content = candidate.content
                text_parts = [p.text for p in raw_content.parts if p.text]
                combined_text = "\n".join(text_parts) if text_parts else None

                function_calls: list[FunctionCallData] = []
                for p in raw_content.parts:
                    if p.function_call and p.function_call.name:
                        raw_args = p.function_call.args
                        if raw_args is None:
                            args_dict = {}
                        elif isinstance(raw_args, dict):
                            args_dict = dict(raw_args)
                        else:
                            try:
                                args_dict = dict(raw_args)
                            except Exception:
                                args_dict = {"input": str(raw_args)}
                        function_calls.append(
                            FunctionCallData(
                                name=p.function_call.name,
                                args=args_dict,
                            )
                        )

                # Extract token usage and compute cost
                prompt_tok = 0
                comp_tok = 0
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    prompt_tok = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                    comp_tok = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

                cost_usd = calculate_cost(target_model, prompt_tok, comp_tok)

                return LLMResponse(
                    text=combined_text,
                    function_calls=function_calls,
                    raw_content=raw_content,
                    token_usage=TokenUsage(
                        prompt_tokens=prompt_tok,
                        completion_tokens=comp_tok,
                        total_tokens=prompt_tok + comp_tok,
                    ),
                    latency_ms=latency_ms,
                    cost_usd=cost_usd,
                )

            except Exception as e:
                err_str = str(e).lower()
                is_retryable = any(
                    code in err_str
                    for code in [
                        "429",
                        "resource_exhausted",
                        "500",
                        "502",
                        "503",
                        "504",
                        "unavailable",
                        "server error",
                        "overloaded",
                        "deadline_exceeded",
                        "timeout",
                        "bad gateway",
                    ]
                )

                if is_retryable and attempt < self.max_retries:
                    sleep_time = min(30.0, backoff + random.uniform(0.1, 0.5))
                    logger.warning(
                        f"LLM call failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}. Retrying in {sleep_time:.2f}s..."
                    )
                    time.sleep(sleep_time)
                    backoff = min(30.0, backoff * 2.0)
                    last_exception = e
                else:
                    raise e

        raise last_exception or RuntimeError("LLM generation failed after retries.")


class FakeLLMProvider(LLMProvider):
    """
    Scriptable mock LLM provider for deterministic offline unit testing.
    Can return queued text responses, function calls, or simulate transient errors.
    """

    def __init__(self, responses: Optional[list[LLMResponse | Exception]] = None) -> None:
        self.responses: list[LLMResponse | Exception] = responses or []
        self.call_history: list[dict[str, Any]] = []

    def queue_response(self, response: LLMResponse | Exception) -> None:
        """Add a scripted response to the front of the queue."""
        self.responses.append(response)

    def generate(
        self,
        contents: list[Any],
        tools: Optional[list[Any]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        model: Optional[str] = None,
    ) -> LLMResponse:
        self.call_history.append({
            "contents": contents,
            "tools": tools,
            "system_instruction": system_instruction,
            "temperature": temperature,
            "model": model,
        })

        if not self.responses:
            # Default empty completion if queue is drained
            return LLMResponse(text="Default mock completion.")

        next_item = self.responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item

        if isinstance(next_item, LLMResponse):
            if next_item.token_usage and next_item.token_usage.total_tokens and not next_item.cost_usd:
                target_model = model or "mock"
                next_item.cost_usd = calculate_cost(
                    target_model,
                    next_item.token_usage.prompt_tokens,
                    next_item.token_usage.completion_tokens,
                )

        return next_item
