import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from spiremind.config import ModelConfig, read_api_key
from spiremind.context.compiler import AgentContext
from spiremind.core.decision import ModelChoice


class ProviderError(RuntimeError):
    pass


class IncompleteModelResponse(ValueError):
    pass


@dataclass(frozen=True)
class ModelResponse:
    choice: ModelChoice
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_present: bool


class OpenAIProvider:
    """SDK-independent Chat Completions transport with validated action-ID output."""

    def __init__(self, config: ModelConfig, client: httpx.AsyncClient | None = None):
        self.config = config
        self._key = read_api_key(config.api_key_env)
        self.client = client or httpx.AsyncClient(timeout=config.timeout_seconds)
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.last_model: str | None = None
        self.reasoning_responses = 0
        self.incomplete_responses = 0
        self.invalid_responses = 0
        self.transport_errors = 0
        self.retryable_http_responses = 0

    async def choose(self, context: AgentContext, legal_ids: set[str]) -> ModelResponse:
        if not self.config.model:
            raise ProviderError("Configure a model ID before requesting decisions")
        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": context.system},
                {"role": "user", "content": context.user},
            ],
            "stream": False,
        }
        if self.config.max_completion_tokens is not None:
            body["max_completion_tokens"] = self.config.max_completion_tokens
        else:
            body["max_tokens"] = self.config.max_tokens
        if self.config.temperature is not None:
            body["temperature"] = self.config.temperature
        if self.config.json_mode:
            body["response_format"] = {"type": "json_object"}
        body.update(self.config.extra_body)
        error = "unknown"
        for attempt in range(self.config.attempts):
            try:
                self.calls += 1
                response = await self.client.post(
                    self.config.base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {self._key}"},
                    json=body,
                )
                if response.status_code in {401, 403, 404}:
                    raise ProviderError(f"Provider HTTP {response.status_code}; check configuration")
                if not response.is_success:
                    error = f"http_{response.status_code}"
                    if response.status_code in {408, 429, 500, 502, 503, 504}:
                        self.retryable_http_responses += 1
                    else:
                        raise ProviderError(f"Provider rejected request: {error}")
                else:
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
                    content = message.get("content")
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError("invalid_content")
                    usage = data.get("usage")
                    if not isinstance(usage, Mapping):
                        usage = {}
                    prompt_tokens = usage.get("prompt_tokens")
                    completion_tokens = usage.get("completion_tokens")
                    if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
                        prompt_tokens = max(1, context.estimated_tokens)
                    if not isinstance(completion_tokens, int) or completion_tokens < 0:
                        completion_tokens = max(1, len(content) // 4)
                    self.input_tokens += prompt_tokens
                    self.output_tokens += completion_tokens
                    model = data.get("model", "")
                    if not isinstance(model, str):
                        raise ValueError("invalid_model")
                    self.last_model = model
                    if self.config.require_exact_model and model != self.config.model:
                        raise ProviderError("Response model does not match requested exact model")
                    reasoning = bool(message.get("reasoning_content") or message.get("reasoning"))
                    self.reasoning_responses += int(reasoning)
                    if item.get("finish_reason") not in {"stop", None}:
                        raise IncompleteModelResponse("incomplete_response")
                    if content.startswith("```json") and content.rstrip().endswith("```"):
                        content = content[7:].rstrip()[:-3].strip()
                    choice = ModelChoice.model_validate_json(content)
                    if choice.action_id not in legal_ids:
                        raise ValueError("invalid_action_id")
                    return ModelResponse(choice, model, prompt_tokens, completion_tokens, reasoning)
            except ProviderError:
                raise
            except httpx.TransportError:
                self.transport_errors += 1
                error = "transport_error"  # Never log headers, raw responses, credentials, or exception text.
            except IncompleteModelResponse:
                self.incomplete_responses += 1
                error = "incomplete_response"
            except (ValueError, ValidationError, KeyError, IndexError, TypeError, json.JSONDecodeError):
                self.invalid_responses += 1
                error = "invalid_model_response"
                body["messages"][-1] = {
                    "role": "user",
                    "content": context.user
                    + "\nReturn valid JSON with one exact legal action_id, confidence and reason.",
                }
            if attempt + 1 < self.config.attempts:
                await asyncio.sleep(min(2**attempt, 4))
        raise ProviderError(f"Provider exhausted {self.config.attempts} attempts: {error}")

    async def close(self):
        await self.client.aclose()
