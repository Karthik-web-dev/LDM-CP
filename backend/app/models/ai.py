"""Models for the AI tutor layer.

``LLMValidationResponse`` is the strict schema the model must return. ``AIFeedback`` is what the
API exposes; it never replaces the deterministic verdict.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: str | None = Field(default=None, max_length=64)
    type: str = Field(max_length=64)
    explanation: str = Field(max_length=2000)


class LLMValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    summary: str = Field(max_length=2000)
    issues: list[LLMIssue] = Field(default_factory=list, max_length=20)
    suggestions: list[str] = Field(default_factory=list, max_length=20)
    concept: str = Field(default="", max_length=2000)


# JSON schema sent to the provider for structured output. Kept explicit (rather than generated
# from the Pydantic model) so it stays within the subset structured outputs support.
LLM_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "component_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "type": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["component_id", "type", "explanation"],
                "additionalProperties": False,
            },
        },
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "concept": {"type": "string"},
    },
    "required": ["valid", "summary", "issues", "suggestions", "concept"],
    "additionalProperties": False,
}


AIErrorKind = Literal[
    "disabled", "timeout", "rate_limited", "auth", "billing", "bad_request", "unavailable",
    "malformed_response", "refused", "truncated", "prompt_too_large", "unknown",
]


class AIFeedback(BaseModel):
    available: bool
    # Why no AI call was made (e.g. the circuit has structural errors that are fully explained).
    skipped_reason: str | None = None
    error: str | None = None
    error_kind: AIErrorKind | None = None

    summary: str | None = None
    issues: list[LLMIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    concept: str | None = None
    # The model's own verdict, kept for transparency. The authoritative verdict is `is_correct`.
    model_verdict: bool | None = None
    agrees_with_analysis: bool | None = None
    anomalies: list[str] = Field(default_factory=list)
    model: str | None = None
