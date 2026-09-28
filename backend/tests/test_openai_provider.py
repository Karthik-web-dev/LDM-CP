"""OpenAI-compatible provider (OpenAI, OpenRouter). The SDK client is stubbed: no network calls."""

import asyncio
import json
from types import SimpleNamespace

import httpx2
import openai
import pytest

from app.ai.client import DisabledAIValidator, OpenAICompatibleAIValidator, create_ai_validator
from app.ai.validator import AIValidationError
from app.config import Settings

GOOD = json.dumps({"valid": True, "summary": "ok", "issues": [], "suggestions": [], "concept": "c"})
REQ = httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def settings(**kw) -> Settings:
    base = {"ai_provider": "openrouter", "ai_api_key": "sk-or-v1-test"}
    return Settings(**{**base, **kw})


def completion(content=GOOD, finish_reason="stop", refusal=None):
    msg = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish_reason)])


def status_error(cls, code):
    return cls("err", response=httpx2.Response(code, request=REQ), body=None)


def run(validator, outcomes):
    """Stub chat.completions.create to return/raise each outcome in turn; return the recorded calls."""
    calls = []
    queue = list(outcomes)

    async def create(**kwargs):
        calls.append(kwargs)
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    validator.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return calls, asyncio.run(validator.validate({"x": 1}))


# ---- configuration ------------------------------------------------------------------------

@pytest.mark.parametrize(
    "key, provider, model",
    [
        ("sk-or-v1-abc", "openrouter", "anthropic/claude-opus-5"),
        ("sk-ant-api03-abc", "anthropic", "claude-opus-5"),
        ("sk-proj-abc", "openai", None),
        ("", "disabled", None),
    ],
)
def test_auto_provider_from_key_prefix(key, provider, model):
    s = Settings(ai_provider="auto", ai_api_key=key)
    assert s.resolved_ai_provider == provider
    assert s.resolved_ai_model == model


def test_openrouter_defaults_and_overrides():
    s = settings()
    assert s.resolved_ai_base_url == "https://openrouter.ai/api/v1"
    s = settings(ai_model="google/gemini-3.5-flash", ai_base_url="https://example.test/v1")
    assert (s.resolved_ai_model, s.resolved_ai_base_url) == ("google/gemini-3.5-flash", "https://example.test/v1")


def test_factory_selects_provider():
    assert isinstance(create_ai_validator(settings()), OpenAICompatibleAIValidator)
    assert isinstance(create_ai_validator(settings(ai_provider="openai", ai_api_key="sk-x")), OpenAICompatibleAIValidator)
    missing = create_ai_validator(settings(ai_api_key=""))
    assert isinstance(missing, DisabledAIValidator)
    with pytest.raises(AIValidationError) as exc:
        asyncio.run(missing.validate({}))
    assert "AI_API_KEY is empty" in exc.value.message


def test_openrouter_client_configuration():
    v = OpenAICompatibleAIValidator(settings(ai_app_url="https://my.app"))
    assert str(v.client.base_url).rstrip("/") == "https://openrouter.ai/api/v1"
    assert v.client.default_headers["X-Title"] == "LDM Circuit Lab"
    assert v.client.default_headers["HTTP-Referer"] == "https://my.app"


# ---- request and response -----------------------------------------------------------------

def test_request_shape_openrouter():
    calls, result = run(OpenAICompatibleAIValidator(settings()), [completion()])
    assert result.valid and result.summary == "ok"
    [req] = calls
    assert req["model"] == "anthropic/claude-opus-5"
    assert [m["role"] for m in req["messages"]] == ["system", "user"]
    assert "<analysis_data>" in req["messages"][1]["content"]
    assert req["response_format"]["type"] == "json_schema" and req["response_format"]["json_schema"]["strict"] is True
    assert req["max_tokens"] == 4000 and "max_completion_tokens" not in req


def test_openai_uses_max_completion_tokens():
    calls, _ = run(OpenAICompatibleAIValidator(settings(ai_provider="openai", ai_api_key="sk-x", ai_model="gpt-5.5")), [completion()])
    assert calls[0]["max_completion_tokens"] == 4000 and "max_tokens" not in calls[0]


def test_falls_back_to_json_object_when_schema_rejected():
    calls, result = run(OpenAICompatibleAIValidator(settings()), [status_error(openai.BadRequestError, 400), completion()])
    assert result.valid
    assert [c["response_format"]["type"] for c in calls] == ["json_schema", "json_object"]


def test_response_format_none():
    calls, _ = run(OpenAICompatibleAIValidator(settings(ai_response_format="none")), [completion()])
    assert "response_format" not in calls[0]


def test_openai_provider_requires_model():
    v = OpenAICompatibleAIValidator(settings(ai_provider="openai", ai_api_key="sk-x"))
    with pytest.raises(AIValidationError) as exc:
        asyncio.run(v.validate({}))
    assert exc.value.kind == "bad_request" and "AI_MODEL" in exc.value.message


@pytest.mark.parametrize(
    "outcomes, kind",
    [
        ([completion(finish_reason="length")], "truncated"),
        ([completion(finish_reason="content_filter")], "refused"),
        ([completion(content=None, refusal="I can't help with that")], "refused"),
        ([completion(content=None)], "malformed_response"),
        ([completion(content="not json")], "malformed_response"),
        ([SimpleNamespace(choices=[])], "unavailable"),
        ([openai.APITimeoutError(request=REQ)], "timeout"),
        ([openai.APIConnectionError(request=REQ)], "unavailable"),
        ([status_error(openai.RateLimitError, 429)], "rate_limited"),
        ([status_error(openai.AuthenticationError, 401)], "auth"),
        ([status_error(openai.NotFoundError, 404)], "bad_request"),
        ([status_error(openai.APIStatusError, 402)], "billing"),
        ([status_error(openai.InternalServerError, 502)], "unavailable"),
        # Schema rejected, then the plain-JSON retry is rejected too.
        ([status_error(openai.BadRequestError, 400), status_error(openai.BadRequestError, 400)], "bad_request"),
    ],
)
def test_error_mapping(outcomes, kind):
    with pytest.raises(AIValidationError) as exc:
        run(OpenAICompatibleAIValidator(settings()), outcomes)
    assert exc.value.kind == kind
