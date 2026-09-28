"""Validate and reconcile LLM output. Never trust that the model returned what was asked for."""

import json

from pydantic import ValidationError

from app.models.ai import AIErrorKind, AIFeedback, LLMIssue, LLMValidationResponse


class AIValidationError(Exception):
    """A failure in the AI layer. ``message`` is safe to show to end users."""

    def __init__(self, kind: AIErrorKind, message: str):
        self.kind = kind
        self.message = message
        super().__init__(f"{kind}: {message}")


def parse_llm_response(text: str) -> LLMValidationResponse:
    text = text.strip()
    # Tolerate a fenced code block even though structured output should not produce one.
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIValidationError("malformed_response", "The AI tutor returned a response that was not valid JSON.") from exc
    try:
        return LLMValidationResponse.model_validate(data)
    except ValidationError as exc:
        raise AIValidationError("malformed_response", "The AI tutor returned a response in an unexpected format.") from exc


def reconcile(
    response: LLMValidationResponse,
    is_correct: bool,
    component_ids: set[str],
    model: str | None,
) -> AIFeedback:
    """Turn a validated LLM response into API feedback, enforcing deterministic authority."""
    anomalies: list[str] = []
    issues: list[LLMIssue] = []
    for issue in response.issues:
        if issue.component_id is not None and issue.component_id not in component_ids:
            anomalies.append(f"The AI referred to a component '{issue.component_id}' that is not in the circuit; the reference was removed.")
            issue = issue.model_copy(update={"component_id": None})
        issues.append(issue)

    agrees = response.valid == is_correct
    if not agrees:
        anomalies.append(
            "The AI tutor's verdict disagreed with the exact circuit analysis. The circuit analysis is authoritative; "
            "treat the AI explanation with caution."
        )

    return AIFeedback(
        available=True,
        summary=response.summary,
        issues=issues,
        suggestions=response.suggestions,
        concept=response.concept or None,
        model_verdict=response.valid,
        agrees_with_analysis=agrees,
        anomalies=anomalies,
        model=model,
    )
