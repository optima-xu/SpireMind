import json

import httpx
import pytest

from spiremind.config import ModelConfig
from spiremind.context.compiler import AgentContext
from spiremind.providers.openai import OpenAIProvider, ProviderError

CTX = AgentContext("x", "Choose JSON", "legal action A", 20, (), ())


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("SPIREMIND_TEST_KEY", "private-test-secret")
    return ModelConfig(
        model="test-model", api_key_env="SPIREMIND_TEST_KEY", attempts=1, require_exact_model=True
    )


def response(choice, model="test-model"):
    return {
        "model": model,
        "choices": [{"message": {"content": json.dumps(choice)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5},
    }


async def test_generic_wire_contract(settings):
    def handler(req):
        body = json.loads(req.content)
        assert body["model"] == "test-model"
        assert body["max_tokens"] == 600
        assert "max_completion_tokens" not in body
        assert "enable_thinking" not in body
        assert "private-test-secret" not in json.dumps(body)
        return httpx.Response(200, json=response({"action_id": "A", "confidence": 0.9, "reason": "ok"}))

    provider = OpenAIProvider(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert (await provider.choose(CTX, {"A"})).choice.action_id == "A"
    assert provider.input_tokens == 20
    await provider.close()


async def test_completion_token_limit_uses_modern_openai_field(settings):
    modern = settings.model_copy(update={"max_completion_tokens": 8192})

    def handler(req):
        body = json.loads(req.content)
        assert body["max_completion_tokens"] == 8192
        assert "max_tokens" not in body
        return httpx.Response(200, json=response({"action_id": "A", "confidence": 0.9, "reason": "ok"}))

    provider = OpenAIProvider(modern, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await provider.choose(CTX, {"A"})
    await provider.close()


async def test_provider_forwards_opt_in_thinking_and_records_reasoning(settings):
    thinking = settings.model_copy(update={"extra_body": {"enable_thinking": True}})

    def handler(req):
        body = json.loads(req.content)
        assert body["enable_thinking"] is True
        data = response({"action_id": "A", "confidence": 0.9, "reason": "ok"})
        data["choices"][0]["message"]["reasoning_content"] = "private chain of thought"
        return httpx.Response(200, json=data)

    provider = OpenAIProvider(thinking, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await provider.choose(CTX, {"A"})
    assert result.reasoning_present
    assert provider.reasoning_responses == 1
    await provider.close()


@pytest.mark.parametrize(
    "choice",
    [
        {"action_id": "INVENTED", "confidence": 0.9, "reason": "x"},
        {"action_id": "A", "confidence": 2, "reason": "x"},
        {"action_id": "A", "confidence": 0.9, "reason": "x", "params": {"target": "invented"}},
        {"action_id": "A", "confidence": float("nan"), "reason": "x"},
        {"action_id": "A", "confidence": "0.9", "reason": "x"},
        {
            "action_id": "A",
            "confidence": 0.9,
            "reason": "x",
            "strategy_update": {"route_preferences": ["x" * 121]},
        },
    ],
)
async def test_malformed_output_never_executes(settings, choice):
    provider = OpenAIProvider(
        settings,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response(choice)))
        ),
    )
    with pytest.raises(ProviderError):
        await provider.choose(CTX, {"A"})
    await provider.close()


async def test_exact_model_required(settings):
    provider = OpenAIProvider(
        settings,
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200, json=response({"action_id": "A", "confidence": 0.9, "reason": "ok"}, "other")
                )
            )
        ),
    )
    with pytest.raises(ProviderError, match="does not match"):
        await provider.choose(CTX, {"A"})
    await provider.close()


async def test_incomplete_response_is_counted_without_exposing_content(settings):
    data = response({"action_id": "A", "confidence": 0.9, "reason": "ok"})
    data["choices"][0]["finish_reason"] = "length"
    provider = OpenAIProvider(
        settings,
        httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=data))),
    )
    with pytest.raises(ProviderError, match="incomplete_response"):
        await provider.choose(CTX, {"A"})
    assert provider.incomplete_responses == 1
    assert provider.invalid_responses == 0
    await provider.close()


async def test_error_body_is_redacted(settings):
    provider = OpenAIProvider(
        settings,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(401, text="private-test-secret"))
        ),
    )
    with pytest.raises(ProviderError) as error:
        await provider.choose(CTX, {"A"})
    assert "private-test-secret" not in str(error.value)
    await provider.close()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"choices": []},
        {"choices": [None]},
        {"choices": [{"message": None}]},
        {"choices": [{"message": {"content": None}}]},
    ],
)
async def test_malformed_response_envelopes_use_provider_error(settings, payload):
    provider = OpenAIProvider(
        settings,
        httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payload))),
    )

    with pytest.raises(ProviderError, match="invalid_model_response"):
        await provider.choose(CTX, {"A"})

    assert provider.invalid_responses == 1
    await provider.close()


async def test_missing_usage_is_estimated_for_runtime_budget(settings):
    data = response({"action_id": "A", "confidence": 0.9, "reason": "ok"})
    data.pop("usage")
    provider = OpenAIProvider(
        settings,
        httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=data))),
    )

    result = await provider.choose(CTX, {"A"})

    assert result.input_tokens == CTX.estimated_tokens
    assert result.output_tokens > 0
    assert provider.input_tokens == CTX.estimated_tokens
    await provider.close()
