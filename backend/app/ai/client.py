"""AI provider abstraction. The rest of the app depends only on ``AIValidator``."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

import anthropic
import openai

from app.ai.prompts import SYSTEM_PROMPT, build_user_message
from app.ai.validator import AIValidationError, parse_llm_response
from app.config import Settings
from app.models.ai import LLM_RESPONSE_JSON_SCHEMA, LLMValidationResponse

logger = logging.getLogger("ldm.ai")


class AIValidator(ABC):
    model_name: str | None = None

    @abstractmethod
    async def validate(self, payload: dict[str, Any], mode: str = "feedback") -> LLMValidationResponse:
        """Return validated tutor feedback, or raise ``AIValidationError``."""


class DisabledAIValidator(AIValidator):
    def __init__(self, message: str = "AI feedback is not configured on this server."):
        self.message = message

    async def validate(self, payload: dict[str, Any], mode: str = "feedback") -> LLMValidationResponse:
        raise AIValidationError("disabled", self.message)


class MockAIValidator(AIValidator):
    """Offline validator for tests and local development without an API key.

    By default it echoes the deterministic verdict with templated text. Tests can inject a fixed
    raw response string (to exercise parsing) or an exception.
    """

    model_name = "mock"

    def __init__(
        self,
        raw_response: str | None = None,
        error: Exception | None = None,
        responder: Callable[[dict[str, Any]], LLMValidationResponse] | None = None,
    ):
        self.raw_response = raw_response
        self.error = error
        self.responder = responder
        self.calls: list[dict[str, Any]] = []
        self.modes: list[str] = []

    async def validate(self, payload: dict[str, Any], mode: str = "feedback") -> LLMValidationResponse:
        self.calls.append(payload)
        self.modes.append(mode)
        if self.error:
            raise self.error
        if self.raw_response is not None:
            return parse_llm_response(self.raw_response)
        if self.responder:
            return self.responder(payload)
        analysis = payload["deterministic_analysis"]
        if mode == "hint":
            return LLMValidationResponse(
                valid=bool(analysis["equivalent_to_expected"]),
                summary="(Mock tutor) Hint: start from the output and ask which gate produces the required behaviour.",
                issues=[], suggestions=["Compare your truth table with the target row by row."], concept="",
            )
        ok = bool(analysis["equivalent_to_expected"])
        mismatched = [c for c in analysis["comparisons"] if not c["equivalent"]]
        return LLMValidationResponse(
            valid=ok,
            summary=(
                "(Mock tutor) Your circuit implements the requested function."
                if ok
                else f"(Mock tutor) {len(mismatched)} output(s) do not match the requested function."
            ),
            issues=[],
            suggestions=[] if ok else ["Compare the counterexample rows in the truth table with the expected output."],
            concept="Two circuits are equivalent when they produce the same output for every input combination.",
        )


class AnthropicAIValidator(AIValidator):
    def __init__(self, settings: Settings):
        kwargs: dict[str, Any] = {"timeout": settings.ai_timeout_seconds, "max_retries": 1}
        if settings.ai_api_key:
            kwargs["api_key"] = settings.ai_api_key.get_secret_value()
        if settings.resolved_ai_base_url:
            kwargs["base_url"] = settings.resolved_ai_base_url
        self.client = anthropic.AsyncAnthropic(**kwargs)
        self.model_name = settings.resolved_ai_model
        self.max_tokens = settings.ai_max_tokens
        self.effort = settings.ai_effort
        self.refusal_fallback = settings.ai_refusal_fallback

    async def validate(self, payload: dict[str, Any], mode: str = "feedback") -> LLMValidationResponse:
        request: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": build_user_message(payload, mode)}],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": LLM_RESPONSE_JSON_SCHEMA},
            },
        }
        try:
            if self.refusal_fallback:
                response = await self.client.beta.messages.create(
                    **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = await self.client.messages.create(**request)
        except anthropic.APITimeoutError as exc:
            raise AIValidationError("timeout", "The AI tutor took too long to respond.") from exc
        except anthropic.RateLimitError as exc:
            raise AIValidationError("rate_limited", "The AI tutor is receiving too many requests. Try again shortly.") from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            logger.error("ai_auth_failed status=%s", exc.status_code)
            raise AIValidationError("auth", "The AI tutor is misconfigured (authentication failed).") from exc
        except anthropic.BadRequestError as exc:
            logger.error("ai_bad_request request_id=%s", getattr(exc, "request_id", None))
            raise AIValidationError("bad_request", "The AI tutor rejected the request (it may be too large).") from exc
        except anthropic.NotFoundError as exc:
            raise AIValidationError("bad_request", "The configured AI model was not found.") from exc
        except anthropic.APIStatusError as exc:
            raise AIValidationError("unavailable", "The AI tutor service is temporarily unavailable.") from exc
        except anthropic.APIConnectionError as exc:
            raise AIValidationError("unavailable", "Could not reach the AI tutor service.") from exc

        if response.stop_reason == "refusal":
            raise AIValidationError("refused", "The AI tutor declined to answer this request.")
        if response.stop_reason == "max_tokens":
            raise AIValidationError("truncated", "The AI tutor's response was cut off.")
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text:
            raise AIValidationError("malformed_response", "The AI tutor returned an empty response.")
        return parse_llm_response(text)


class OpenAICompatibleAIValidator(AIValidator):
    """OpenAI chat-completions API: OpenAI itself, OpenRouter, or any compatible gateway (AI_BASE_URL)."""

    def __init__(self, settings: Settings):
        self.provider = settings.resolved_ai_provider
        headers: dict[str, str] = {}
        if self.provider == "openrouter":
            # Optional attribution headers recognised by OpenRouter.
            headers["X-Title"] = "LDM Circuit Lab"
            if settings.ai_app_url:
                headers["HTTP-Referer"] = settings.ai_app_url
        self.client = openai.AsyncOpenAI(
            api_key=settings.ai_api_key.get_secret_value(),  # presence checked in create_ai_validator
            base_url=settings.resolved_ai_base_url or openai.NOT_GIVEN,
            timeout=settings.ai_timeout_seconds,
            max_retries=1,
            default_headers=headers or None,
        )
        self.model_name = settings.resolved_ai_model
        self.max_tokens = settings.ai_max_tokens
        self.response_format = settings.ai_response_format

    def _format_param(self, kind: str) -> dict[str, Any] | None:
        if kind == "json_schema":
            return {
                "type": "json_schema",
                "json_schema": {"name": "circuit_feedback", "strict": True, "schema": LLM_RESPONSE_JSON_SCHEMA},
            }
        if kind == "json_object":
            return {"type": "json_object"}
        return None

    async def _create(self, payload: dict[str, Any], response_format: str, mode: str):
        request: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(payload, mode)},
            ],
        }
        # OpenAI's own API wants max_completion_tokens; OpenRouter and most gateways use max_tokens.
        request["max_completion_tokens" if self.provider == "openai" else "max_tokens"] = self.max_tokens
        fmt = self._format_param(response_format)
        if fmt:
            request["response_format"] = fmt
        return await self.client.chat.completions.create(**request)

    async def validate(self, payload: dict[str, Any], mode: str = "feedback") -> LLMValidationResponse:
        if not self.model_name:
            raise AIValidationError("bad_request", "No AI model is configured. Set AI_MODEL in backend/.env.")
        try:
            try:
                response = await self._create(payload, self.response_format, mode)
            except openai.BadRequestError:
                # Some models reject strict JSON-schema output; retry once asking for plain JSON.
                if self.response_format != "json_schema":
                    raise
                logger.info("ai_response_format_fallback model=%s", self.model_name)
                response = await self._create(payload, "json_object", mode)
        except openai.APITimeoutError as exc:
            raise AIValidationError("timeout", "The AI tutor took too long to respond.") from exc
        except openai.RateLimitError as exc:
            raise AIValidationError("rate_limited", "The AI tutor is receiving too many requests. Try again shortly.") from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            logger.error("ai_auth_failed status=%s", exc.status_code)
            raise AIValidationError("auth", "The AI tutor is misconfigured (authentication failed). Check AI_API_KEY.") from exc
        except openai.NotFoundError as exc:
            raise AIValidationError("bad_request", f"The AI model '{self.model_name}' was not found. Check AI_MODEL.") from exc
        except openai.BadRequestError as exc:
            logger.error("ai_bad_request status=%s", exc.status_code)
            raise AIValidationError("bad_request", "The AI tutor rejected the request (it may be too large, or the model may not support it).") from exc
        except openai.APIStatusError as exc:
            if exc.status_code == 402:
                raise AIValidationError("billing", "The AI provider account has insufficient credits.") from exc
            raise AIValidationError("unavailable", "The AI tutor service is temporarily unavailable.") from exc
        except openai.APIConnectionError as exc:
            raise AIValidationError("unavailable", "Could not reach the AI tutor service.") from exc

        # Gateways can return HTTP 200 with an error body and no choices.
        if not getattr(response, "choices", None):
            raise AIValidationError("unavailable", "The AI tutor service returned no answer.")
        choice = response.choices[0]
        message = choice.message
        if getattr(message, "refusal", None) or choice.finish_reason == "content_filter":
            raise AIValidationError("refused", "The AI tutor declined to answer this request.")
        if choice.finish_reason == "length":
            raise AIValidationError("truncated", "The AI tutor's response was cut off.")
        if not message.content:
            raise AIValidationError("malformed_response", "The AI tutor returned an empty response.")
        return parse_llm_response(message.content)


def create_ai_validator(settings: Settings) -> AIValidator:
    provider = settings.resolved_ai_provider
    if provider == "anthropic":
        return AnthropicAIValidator(settings)
    if provider in ("openai", "openrouter"):
        if not (settings.ai_api_key and settings.ai_api_key.get_secret_value().strip()):
            return DisabledAIValidator(f"AI_PROVIDER is {provider} but AI_API_KEY is empty.")
        return OpenAICompatibleAIValidator(settings)
    if provider == "mock":
        return MockAIValidator()
    return DisabledAIValidator()
