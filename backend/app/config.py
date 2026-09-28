"""Application configuration, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Limits(BaseSettings):
    """Request-size guards. Every value can be overridden with a LIMIT_* environment variable."""

    model_config = SettingsConfigDict(
        env_prefix="LIMIT_", env_file=BACKEND_DIR / ".env", extra="ignore"
    )

    max_inputs: int = 12
    max_gates: int = 200
    max_outputs: int = 16
    max_connections: int = 1000
    max_label_length: int = 32
    # Truth tables have 2^n rows; 12 variables -> 4096 rows.
    max_truth_table_variables: int = 12
    max_expression_length: int = 4000
    max_ai_prompt_chars: int = 60_000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # "auto" picks the provider from the AI_API_KEY prefix (sk-or- -> openrouter, sk-ant- -> anthropic,
    # other sk- -> openai) and disables AI feedback when no key is set.
    ai_provider: Literal["auto", "anthropic", "openai", "openrouter", "mock", "disabled"] = "auto"
    ai_api_key: SecretStr | None = None
    # Defaults per provider when unset: see DEFAULT_MODELS. The OpenAI provider requires it.
    ai_model: str | None = None
    # Defaults per provider when unset: see DEFAULT_BASE_URLS.
    ai_base_url: str | None = None
    ai_timeout_seconds: float = 60.0
    ai_max_tokens: int = 4000
    # Anthropic provider only.
    ai_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    # Server-side refusal fallback (Anthropic provider only; disable when AI_BASE_URL points at a
    # proxy that does not support beta parameters).
    ai_refusal_fallback: bool = True
    # OpenAI-compatible providers: how to request JSON. "json_schema" (strict structured output) falls
    # back to "json_object" automatically if the model rejects it; "none" relies on the prompt alone.
    ai_response_format: Literal["json_schema", "json_object", "none"] = "json_schema"
    # Optional OpenRouter attribution (shown on openrouter.ai); sent as the HTTP-Referer header.
    ai_app_url: str | None = None
    # Ask the AI tutor for feedback even when the deterministic analysis says the circuit is correct.
    ai_on_correct: bool = True

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"

    limits: Limits = Field(default_factory=Limits)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_ai_provider(self) -> str:
        if self.ai_provider != "auto":
            return self.ai_provider
        key = self.ai_api_key.get_secret_value().strip() if self.ai_api_key else ""
        if not key:
            return "disabled"
        if key.startswith("sk-or-"):
            return "openrouter"
        if key.startswith("sk-ant-"):
            return "anthropic"
        if key.startswith("sk-"):
            return "openai"
        return "anthropic"

    @property
    def resolved_ai_model(self) -> str | None:
        return self.ai_model or DEFAULT_MODELS.get(self.resolved_ai_provider)

    @property
    def resolved_ai_base_url(self) -> str | None:
        return self.ai_base_url or DEFAULT_BASE_URLS.get(self.resolved_ai_provider)


DEFAULT_MODELS = {
    "anthropic": "claude-opus-5",
    # OpenRouter model ids are "<vendor>/<model>"; see https://openrouter.ai/models.
    "openrouter": "anthropic/claude-opus-5",
}

DEFAULT_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
}


@lru_cache
def get_settings() -> Settings:
    return Settings()
