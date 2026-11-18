"""Circuit generation: ask the AI for a circuit, verify it, retry with the exact problems, fall back safely.

The model is never trusted. A circuit reaches the student only after the same deterministic analysis
that checks student circuits says it solves the task. If the AI fails, times out, or cannot get it
right within the attempt limit, the response says so and, where it is safe, shows a stored circuit.

Three intents:

* ``target``: build from scratch to the selected target. Fallback: the stored circuit for that exercise.
* ``describe``: only a plain-language request. The AI states a precise ``spec`` of what it will build and
  the circuit is checked against that spec (it catches wiring mistakes, not a misread request, so the
  spec is returned for the student to confirm). Fallback: a stored circuit whose name matches the request.
* ``extend``: improve the student's existing circuit so it meets the target. Their parts keep their
  positions. On failure nothing is returned, so the student's circuit is never replaced by a fallback.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.ai.client import AIValidator
from app.ai.validator import AIValidationError
from app.config import Settings
from app.generator.layout import apply_layout, positions_of
from app.generator.prompts import (
    build_describe_message,
    build_extend_message,
    build_system_prompt,
    build_user_message,
)
from app.models.analysis import DeterministicResult
from app.models.circuit import Circuit
from app.models.task import Task
from app.services.demo_matcher import DemoMatcher
from app.services.golden_repository import GoldenRepository
from app.services.validation_service import ValidationService

logger = logging.getLogger("ldm.generation")

_ALLOWED = {
    "inputs": {"id", "label"},
    "gates": {"id", "type", "inputs"},
    "outputs": {"id", "label"},
    "connections": {"from", "to", "input_index", "output_index"},
}
_SPEC_KEYS = {"inputs", "outputs", "expected_outputs", "expected_truth_table", "sequence"}


# Provider problems worth another try: a hiccup should not cost the student the whole build.
TRANSIENT_ERRORS = {"unavailable", "rate_limited", "timeout", "malformed_response", "truncated"}


class RequestDeclined(ValueError):
    """The AI says the request is not a digital logic circuit it can build."""


@dataclass
class GenerationResult:
    success: bool
    source: str  # "ai" | "stored" | "fallback" | "none"
    circuit: dict[str, Any] | None = None
    explanation: str | None = None
    attempts: int = 0
    notice: str | None = None
    model: str | None = None
    # describe intent: the target the AI says it built to (a task the student can adopt as their target).
    spec: dict[str, Any] | None = None
    # A stored circuit was shown for this exercise (the workspace should switch to it).
    matched_task_id: str | None = None


def extract_reply(raw: str) -> tuple[dict[str, Any], str | None, Any]:
    """Pull the circuit, the explanation and the optional spec out of a model reply.

    Tolerates markdown fences and prose around the JSON, accepts either ``{"circuit": {...}}`` or a
    bare circuit, and drops fields the schema does not know instead of failing on them.
    """
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The reply did not contain a JSON object.")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"The reply was not valid JSON ({exc.msg}).") from exc
    if not isinstance(data, dict):
        raise ValueError("The reply JSON must be an object.")
    if isinstance(data.get("unsupported"), str):
        raise RequestDeclined(data["unsupported"][:300])
    explanation = data.get("explanation") if isinstance(data.get("explanation"), str) else None
    circuit = data.get("circuit", data)
    if not isinstance(circuit, dict):
        raise ValueError('"circuit" must be an object.')
    cleaned: dict[str, Any] = {"version": 1}
    for key, allowed in _ALLOWED.items():
        items = circuit.get(key, [])
        if not isinstance(items, list):
            raise ValueError(f'"{key}" must be a list.')
        cleaned[key] = [{k: v for k, v in item.items() if k in allowed and v is not None} for item in items if isinstance(item, dict)]
    return cleaned, explanation, data.get("spec")


def extract_circuit(raw: str) -> tuple[dict[str, Any], str | None]:
    circuit, explanation, _ = extract_reply(raw)
    return circuit, explanation


def task_from_spec(request: str, spec: Any) -> Task:
    """The target the AI says it built to, as a task. Raises ``ValueError`` with a message the AI can act on."""
    if not isinstance(spec, dict):
        raise ValueError('The reply needs a "spec" object stating exactly what the circuit does.')
    data = {k: v for k, v in spec.items() if k in _SPEC_KEYS}
    text = request.strip()
    try:
        return Task.model_validate({"id": "described", "title": (text[:60] or "Described circuit"), "description": text[:1000], **data})
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5])
        raise ValueError(f"The spec is not valid: {details}") from exc


def describe_failure(det: DeterministicResult) -> str:
    lines: list[str] = []
    for e in det.errors[:8]:
        lines.append(f"- {e.message}")
    if not lines and det.sequence is not None:
        for r in [r for r in det.sequence.rows if not r.ok][:4]:
            lines.append(f"- After clock pulse {r.step} (inputs set: {r.inputs or 'none'}) expected {r.expected} but the circuit gave {r.actual}.")
    if not lines:
        for c in det.comparisons:
            if c.equivalent:
                continue
            if c.circuit_output is None:
                lines.append(f"- There is no output labelled {c.expected_output}.")
            for ce in c.counterexamples[:3]:
                lines.append(f"- Output {c.expected_output}: with inputs {ce.inputs} expected {ce.expected} but the circuit gave {ce.actual}.")
    return "\n".join(lines) or "- The circuit does not match the target."


def _is_correct(det: DeterministicResult) -> bool:
    return det.structurally_valid and not det.errors and det.equivalent_to_expected


class GenerationService:
    def __init__(
        self, ai: AIValidator, validation: ValidationService, golden: GoldenRepository, settings: Settings,
        matcher: DemoMatcher | None = None,
    ):
        self.ai = ai
        self.validation = validation
        self.golden = golden
        self.settings = settings
        self.matcher = matcher

    # ---- stored circuits -------------------------------------------------------------------

    def _stored(self, task_id: str, source: str, notice: str | None) -> GenerationResult | None:
        stored = self.golden.get(task_id)
        if stored is None:
            return None
        return GenerationResult(
            True, source, stored["circuit"], explanation=f"Stored {stored.get('source', 'reference')} circuit.",
            attempts=0, notice=notice, matched_task_id=task_id,
        )

    def _stored_for_request(self, request: str, source: str, notice: str, strict: bool) -> GenerationResult | None:
        """A stored circuit whose name matches a plain-language request (deterministic text matching).

        After an AI failure the match is strict: the request must really *name* that circuit, so a stored
        circuit is never shown for a different one that merely shares a word ("sr flip flop using NAND
        gates" is not the NAND-gate exercise).
        """
        best = self.matcher.best(request, strict=strict) if self.matcher and request.strip() else None
        if best is None:
            return None
        return self._stored(best.task_id, source, f'{notice} Matched "{best.title}".')

    # ---- live generation -------------------------------------------------------------------

    async def _attempts(
        self, intent: str, task: Task | None, user_prompt: str | None, existing: Circuit | None,
    ) -> GenerationResult | tuple[str, int]:
        """Run the attempt loop. Returns a result on success, or (last problem, attempts) on failure."""
        with_spec = intent == "describe"
        system = build_system_prompt(with_spec)
        target = self.validation.describe_target(task) if task is not None else {}
        current: dict[str, Any] | None = None
        status = ""
        keep: dict[str, tuple[float, float]] | None = None
        if intent == "extend":
            assert task is not None and existing is not None
            current = existing.model_dump(by_alias=True, exclude_none=True, exclude={
                "inputs": {"__all__": {"position"}}, "gates": {"__all__": {"position"}}, "outputs": {"__all__": {"position"}},
            })
            keep = positions_of(existing.model_dump(by_alias=True, exclude_none=True))
            before = self.validation.analyze(task, existing)
            status = "It already matches the target." if _is_correct(before) else describe_failure(before)

        previous: tuple[str, str] | None = None
        last_problem = "No attempt was made."
        attempts = 0
        for _ in range(max(1, self.settings.generate_attempts)):
            attempts += 1
            if intent == "describe":
                user = build_describe_message(user_prompt or "", previous)
            elif intent == "extend":
                user = build_extend_message(task, target, current or {}, status, user_prompt, previous)  # type: ignore[arg-type]
            else:
                user = build_user_message(task, target, user_prompt, previous)  # type: ignore[arg-type]
            try:
                raw = await self.ai.complete_json(system, user)
            except AIValidationError as exc:
                if exc.kind not in TRANSIENT_ERRORS:
                    raise
                last_problem = exc.message
                previous = None  # nothing to correct: ask again
                logger.info("generation_attempt_provider_error attempt=%d kind=%s", attempts, exc.kind)
                await asyncio.sleep(1)
                continue
            try:
                data, explanation, spec = extract_reply(raw)
                circuit = Circuit.model_validate(data)
                check_task = task_from_spec(user_prompt or "", spec) if with_spec else task
            except RequestDeclined as exc:
                return GenerationResult(False, "none", attempts=attempts, notice=f"The AI says this is not something it can build as a digital logic circuit: {exc}")
            except ValueError as exc:  # includes pydantic's ValidationError
                last_problem = f"- The reply was invalid: {str(exc)[:400]}"
                previous = (raw[:1500], last_problem)
                logger.info("generation_attempt_invalid attempt=%d", attempts)
                continue
            assert check_task is not None

            if with_spec:
                wrong = self._label_problems(check_task, circuit)
                if wrong:
                    last_problem = wrong
                    previous = (json.dumps(data, separators=(",", ":")), last_problem)
                    continue
            det = self.validation.analyze(check_task, circuit)
            if _is_correct(det):
                placed = apply_layout(circuit.model_dump(by_alias=True, exclude_none=True), keep)
                logger.info("generation_succeeded intent=%s attempts=%d", intent, attempts)
                return GenerationResult(
                    True, "ai", placed, explanation, attempts, None, self.ai.model_name,
                    spec=check_task.model_dump(exclude_none=True) if with_spec else None,
                )
            last_problem = describe_failure(det)
            previous = (json.dumps(data, separators=(",", ":")), last_problem)
            logger.info("generation_attempt_failed attempt=%d", attempts)
        return last_problem, attempts

    @staticmethod
    def _label_problems(task: Task, circuit: Circuit) -> str:
        """The circuit's labels must be the ones its own spec states."""
        lines = []
        wanted_out = set(task.output_labels())
        have_out = {o.label for o in circuit.outputs}
        if wanted_out != have_out:
            lines.append(f"- The circuit's outputs are {sorted(have_out)} but the spec's outputs are {sorted(wanted_out)}; they must be identical.")
        if task.inputs and set(task.inputs) != {i.label for i in circuit.inputs}:
            lines.append(f"- The circuit's inputs are {sorted(i.label for i in circuit.inputs)} but the spec's inputs are {sorted(task.inputs)}; they must be identical.")
        return "\n".join(lines)

    async def _guarded(self, intent: str, task: Task | None, user_prompt: str | None, existing: Circuit | None) -> GenerationResult | tuple[str, int]:
        """Run the attempts, turning every AI problem into a plain failure message."""
        try:
            return await asyncio.wait_for(
                self._attempts(intent, task, user_prompt, existing), timeout=self.settings.generate_timeout_seconds
            )
        except asyncio.TimeoutError:
            return "The AI took too long to answer.", 0
        except AIValidationError as exc:
            return exc.message, 0
        except Exception:  # never let an AI problem break the demo
            logger.exception("generation_failed_unexpectedly")
            return "The AI service failed unexpectedly.", 0

    async def generate(
        self, task: Task | None, user_prompt: str | None = None, mode: str = "live",
        intent: str = "target", existing: Circuit | None = None,
    ) -> GenerationResult:
        if intent == "describe":
            return await self._describe(user_prompt or "", mode)
        if task is None:
            return GenerationResult(False, "none", notice="Pick a target first.")
        if intent == "extend":
            return await self._extend(task, user_prompt, existing)

        # intent == "target": build from scratch for the selected target
        if mode == "demo":
            stored = self._stored(task.id, "stored", "Demo mode: showing the stored circuit.")
            return stored or GenerationResult(False, "none", notice="Demo mode is on, but no stored circuit exists for this exercise.")

        outcome = await self._guarded("target", task, user_prompt, None)
        if isinstance(outcome, GenerationResult):
            return outcome
        problem, attempts = outcome
        failure = f"The AI could not produce a correct circuit in {attempts} attempt(s).\n{problem}" if attempts else problem
        fallback = self._stored(task.id, "fallback", f"{failure} Showing the stored circuit instead.")
        if fallback is not None:
            fallback.attempts = attempts
            return fallback
        return GenerationResult(False, "none", attempts=attempts, notice=failure)

    async def _describe(self, request: str, mode: str) -> GenerationResult:
        if not request.strip():
            return GenerationResult(False, "none", notice="Describe the circuit you want first.")
        if mode == "demo":
            stored = self._stored_for_request(request, "stored", "Demo mode: showing a stored circuit.", strict=False)
            return stored or GenerationResult(False, "none", notice=f'Demo mode is on and no stored circuit matches "{request.strip()[:80]}".')

        outcome = await self._guarded("describe", None, request, None)
        if isinstance(outcome, GenerationResult):
            if outcome.success:
                outcome.notice = (
                    "Checked against the AI's own reading of your request (the target below). "
                    "Make sure that is what you meant."
                )
            return outcome  # a declined request is reported as it is: no stored circuit is shown instead
        problem, attempts = outcome
        failure = f"The AI could not produce a correct circuit in {attempts} attempt(s).\n{problem}" if attempts else problem
        fallback = self._stored_for_request(request, "fallback", f"{failure} Showing a stored circuit instead.", strict=True)
        if fallback is not None:
            fallback.attempts = attempts
            return fallback
        return GenerationResult(False, "none", attempts=attempts, notice=failure)

    async def _extend(self, task: Task, user_prompt: str | None, existing: Circuit | None) -> GenerationResult:
        if existing is None or not (existing.inputs or existing.gates or existing.outputs):
            return GenerationResult(False, "none", notice="There is no circuit on the workspace to build on.")
        if not (user_prompt or "").strip():
            before = self.validation.analyze(task, existing)
            if _is_correct(before):
                return GenerationResult(
                    True, "none", None, attempts=0,
                    notice="Your circuit already matches the target, so there is nothing to improve. Say what you want changed to continue.",
                )
        outcome = await self._guarded("extend", task, user_prompt, existing)
        if isinstance(outcome, GenerationResult):
            return outcome
        problem, attempts = outcome
        failure = f"The AI could not complete your circuit in {attempts} attempt(s).\n{problem}" if attempts else problem
        return GenerationResult(False, "none", attempts=attempts, notice=f"{failure}\nYour circuit was not changed.")
