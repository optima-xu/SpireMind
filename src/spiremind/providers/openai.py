import asyncio
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from spiremind.config import ModelConfig, read_api_key
from spiremind.context.compiler import AgentContext
from spiremind.core.decision import ModelChoice

from .calculator import TOOL, execute_calculator

MAX_TOOL_ROUNDS = 4
MAX_TOOL_CALLS_PER_ROUND = 8


class ProviderError(RuntimeError):
    pass


class IncompleteModelResponse(ValueError):
    pass


class RetryableHTTP(ValueError):
    pass


@dataclass(frozen=True)
class ModelResponse:
    choice: ModelChoice
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_present: bool
    calculations: tuple[dict[str, str], ...] = ()


class OpenAIProvider:
    """SDK-independent Chat Completions transport with validated action-ID output."""

    def __init__(self, config: ModelConfig, client: httpx.AsyncClient | None = None):
        self.config = config
        self._key = read_api_key(config.api_key_env)
        self.client = client or httpx.AsyncClient(timeout=config.timeout_seconds)
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.calculator_calls = 0
        self.last_model: str | None = None
        self.reasoning_responses = 0
        self.incomplete_responses = 0
        self.invalid_responses = 0
        self.transport_errors = 0
        self.retryable_http_responses = 0

    def _body(self, messages: list[dict], first_round: bool) -> dict:
        body = {"model": self.config.model, "messages": messages, "stream": False}
        if self.config.max_completion_tokens is not None:
            body["max_completion_tokens"] = self.config.max_completion_tokens
        else:
            body["max_tokens"] = self.config.max_tokens
        if self.config.temperature is not None:
            body["temperature"] = self.config.temperature
        if self.config.reasoning_effort is not None:
            body["reasoning_effort"] = self.config.reasoning_effort
        if self.config.json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.config.calculator_mode != "off":
            body["tools"] = [TOOL]
            body["tool_choice"] = (
                "required" if first_round and self.config.calculator_mode == "required" else "auto"
            )
        body.update(self.config.extra_body)
        return body

    async def _completion(
        self, body: dict, estimated_tokens: int
    ) -> tuple[Mapping, Mapping, str, int, int, bool]:
        self.calls += 1
        response = await self.client.post(
            self.config.base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {self._key}"},
            json=body,
        )
        if response.status_code in {401, 403, 404}:
            raise ProviderError(f"Provider HTTP {response.status_code}; check configuration")
        if not response.is_success:
            code = response.status_code
            if code in {408, 429, 500, 502, 503, 504}:
                self.retryable_http_responses += 1
                raise RetryableHTTP(f"http_{code}")
            raise ProviderError(f"Provider rejected request: http_{code}")
        data = response.json()
        if not isinstance(data, Mapping):
            raise ValueError("invalid_response_envelope")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("invalid_choices")
        item = choices[0]
        if not isinstance(item, Mapping):
            raise ValueError("invalid_choice")
        message = item.get("message")
        if not isinstance(message, Mapping):
            raise ValueError("invalid_message")
        if message.get("tool_calls") is None and not isinstance(message.get("content"), str):
            raise ValueError("invalid_content")
        model = data.get("model", "")
        if not isinstance(model, str):
            raise ValueError("invalid_model")
        self.last_model = model
        if self.config.require_exact_model and model != self.config.model:
            raise ProviderError("Response model does not match requested exact model")
        content = message.get("content")
        usage = data.get("usage")
        if not isinstance(usage, Mapping):
            usage = {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
            prompt_tokens = max(1, estimated_tokens)
        if not isinstance(completion_tokens, int) or completion_tokens < 0:
            completion_tokens = max(1, len(content or json.dumps(message)) // 4)
        self.input_tokens += prompt_tokens
        self.output_tokens += completion_tokens
        reasoning = bool(message.get("reasoning_content") or message.get("reasoning"))
        self.reasoning_responses += int(reasoning)
        if item.get("finish_reason") not in {"stop", "tool_calls", None}:
            raise IncompleteModelResponse("incomplete_response")
        return item, message, model, prompt_tokens, completion_tokens, reasoning

    @staticmethod
    def _tool_messages(message: Mapping) -> tuple[dict, list[dict], list[dict[str, str]]]:
        calls = message.get("tool_calls")
        if not isinstance(calls, list) or not 1 <= len(calls) <= MAX_TOOL_CALLS_PER_ROUND:
            raise ValueError("invalid_tool_calls")
        echoed = []
        results = []
        trace = []
        seen_ids = set()
        for call in calls:
            if not isinstance(call, Mapping) or call.get("type") != "function":
                raise ValueError("invalid_tool_call")
            call_id = call.get("id")
            function = call.get("function")
            if not isinstance(call_id, str) or not 1 <= len(call_id) <= 128 or call_id in seen_ids:
                raise ValueError("invalid_tool_call_id")
            seen_ids.add(call_id)
            if not isinstance(function, Mapping) or function.get("name") != "calculate":
                raise ValueError("unknown_tool")
            arguments = function.get("arguments")
            if not isinstance(arguments, str) or len(arguments) > 2048:
                raise ValueError("invalid_tool_arguments")
            computation = execute_calculator(arguments)
            echoed.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "calculate", "arguments": arguments},
                }
            )
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(computation, separators=(",", ":")),
                }
            )
            trace.extend(computation)
        assistant = {"role": "assistant", "content": message.get("content") or "", "tool_calls": echoed}
        return assistant, results, trace

    @staticmethod
    def _parse_choice(content: str) -> ModelChoice:
        # Some compatible endpoints ignore JSON mode on the turn after a tool
        # response and wrap the JSON in explanatory prose or a code fence.
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL | re.IGNORECASE)
        candidate = fenced.group(1) if fenced else content.strip()
        try:
            return ModelChoice.model_validate_json(candidate)
        except ValidationError as original:
            if fenced:
                raise
            start = candidate.find("{")
            if start < 0:
                raise
            value, end = json.JSONDecoder().raw_decode(candidate[start:])
            if "{" in candidate[start + end :]:
                raise ValueError("multiple_json_objects") from original
            return ModelChoice.model_validate(value)

    async def choose(self, context: AgentContext, legal_ids: set[str]) -> ModelResponse:
        if not self.config.model:
            raise ProviderError("Configure a model ID before requesting decisions")
        error = "unknown"
        decision_input = decision_output = 0
        for attempt in range(self.config.attempts):
            messages = [
                {"role": "system", "content": context.system},
                {"role": "user", "content": context.user},
            ]
            if attempt:
                messages[-1]["content"] += (
                    "\nReturn one exact legal action_id in JSON. Use the calculator tool for every "
                    "arithmetic comparison and base your reason on its results."
                )
            calculations: list[dict[str, str]] = []
            reasoning_present = False
            try:
                for round_index in range(MAX_TOOL_ROUNDS + 1):
                    body = self._body(messages, round_index == 0)
                    (
                        item,
                        message,
                        model,
                        prompt_tokens,
                        completion_tokens,
                        reasoning,
                    ) = await self._completion(body, context.estimated_tokens)
                    decision_input += prompt_tokens
                    decision_output += completion_tokens
                    reasoning_present |= reasoning
                    if message.get("tool_calls") is not None:
                        if self.config.calculator_mode == "off" or round_index == MAX_TOOL_ROUNDS:
                            raise ValueError("unexpected_or_excess_tool_calls")
                        assistant, tool_messages, trace = self._tool_messages(message)
                        messages.extend([assistant, *tool_messages])
                        calculations.extend(trace)
                        self.calculator_calls += len(tool_messages)
                        continue
                    if item.get("finish_reason") == "tool_calls":
                        raise ValueError("missing_tool_calls")
                    content = message.get("content")
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError("invalid_content")
                    if self.config.calculator_mode == "required" and not any(
                        "result" in entry for entry in calculations
                    ):
                        raise ValueError("calculator_required")
                    choice = self._parse_choice(content)
                    if choice.action_id not in legal_ids:
                        raise ValueError("invalid_action_id")
                    return ModelResponse(
                        choice,
                        model,
                        decision_input,
                        decision_output,
                        reasoning_present,
                        tuple(calculations),
                    )
                raise ValueError("tool_round_limit")
            except ProviderError:
                raise
            except httpx.TransportError:
                self.transport_errors += 1
                error = "transport_error"  # Never log headers, raw responses, credentials, or exception text.
            except RetryableHTTP as failure:
                error = str(failure)
            except IncompleteModelResponse:
                self.incomplete_responses += 1
                error = "incomplete_response"
            except (ValueError, ValidationError, KeyError, IndexError, TypeError, json.JSONDecodeError):
                self.invalid_responses += 1
                error = "invalid_model_response"
            if attempt + 1 < self.config.attempts:
                await asyncio.sleep(min(2**attempt, 4))
        raise ProviderError(f"Provider exhausted {self.config.attempts} attempts: {error}")

    async def close(self):
        await self.client.aclose()
