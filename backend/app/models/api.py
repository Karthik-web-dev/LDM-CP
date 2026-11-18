"""HTTP request/response models for /api/v1."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.ai import AIFeedback
from app.models.analysis import DeterministicResult, KMap, TruthTable
from app.models.circuit import Circuit
from app.models.task import Task


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Either reference a built-in task by id or send a full task definition.
    task_id: str | None = Field(default=None, max_length=64)
    task: Task | None = None
    circuit: Circuit
    # Skip the AI tutor for this request (e.g. quick checks while editing).
    include_ai: bool = True
    # "feedback": explain the verdict (skipped while the circuit has structural errors).
    # "hint": a nudge towards the next step, available at any stage, even for an empty canvas.
    ai_mode: Literal["feedback", "hint"] = "feedback"

    @model_validator(mode="after")
    def _one_task(self) -> "ValidateRequest":
        if (self.task_id is None) == (self.task is None):
            raise ValueError("Provide exactly one of task_id or task")
        return self


class ValidateResponse(BaseModel):
    success: bool
    # Authoritative verdict: structurally valid AND logically equivalent to the task.
    is_correct: bool
    task: Task
    deterministic: DeterministicResult
    ai: AIFeedback


class TaskPreview(BaseModel):
    """A target described both ways, so the user can check it before building the circuit."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    # Label -> equation (as typed for equation targets; simplified from the table for table targets).
    expressions: dict[str, str] = Field(default_factory=dict)
    # Label -> simplified sum-of-products equivalent of the target.
    simplified: dict[str, str] = Field(default_factory=dict)
    truth_table: TruthTable | None = None


class KMapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str | None = Field(default=None, max_length=64)
    task: Task | None = None
    # "target": the function to build. "circuit": what the circuit computes (needs `circuit`).
    source: Literal["target", "circuit"] = "target"
    circuit: Circuit | None = None

    @model_validator(mode="after")
    def _check(self) -> "KMapRequest":
        if (self.task_id is None) == (self.task is None):
            raise ValueError("Provide exactly one of task_id or task")
        if self.source == "circuit" and self.circuit is None:
            raise ValueError("source 'circuit' needs a circuit")
        return self


class KMapResponse(BaseModel):
    source: Literal["target", "circuit"]
    kmaps: list[KMap] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str | None = Field(default=None, max_length=64)
    task: Task | None = None
    prompt: str | None = Field(default=None, max_length=1000)  # optional extra instructions
    # "live" asks the AI (with retries and a stored-circuit fallback); "demo" only uses the stored circuit.
    mode: Literal["live", "demo"] = "live"
    # "describe": plain-language request only, no target (the AI states what it builds and is checked against that).
    # "target": build from scratch for the given target. "extend": improve `circuit` so it meets the given target.
    intent: Literal["describe", "target", "extend"] = "target"
    circuit: Circuit | None = None  # the student's current circuit, for intent "extend"


class GenerateResponse(BaseModel):
    success: bool
    # "ai": verified AI circuit. "stored": demo mode. "fallback": the AI failed, the stored circuit is shown. "none": nothing.
    source: Literal["ai", "stored", "fallback", "none"]
    circuit: Circuit | None = None
    explanation: str | None = None
    attempts: int = 0
    notice: str | None = None
    model: str | None = None
    # intent "describe": the target the AI says it built to, so it can be adopted as the student's target.
    spec: Task | None = None
    # A stored circuit for this exercise was shown (the workspace should switch to that exercise).
    matched_task_id: str | None = None


class DemoMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(max_length=300)
    # Strict: only distinctive circuit names count (used to decide whether live AI text names a circuit).
    strict: bool = False


class DemoEntryOut(BaseModel):
    task_id: str
    title: str
    style: Literal["gates", "ic"]  # stored circuit built from basic gates, or using an IC / block
    parts: list[str]


class DemoMatchOut(BaseModel):
    task_id: str
    title: str
    style: Literal["gates", "ic"]
    score: float
    phrase: str  # the stored phrase your words matched
    full: bool  # a whole phrase matched (False: only a suggestion)


class DemoMatchResponse(BaseModel):
    # The circuit to open (a whole stored phrase was matched), or None when only suggestions exist.
    best: DemoMatchOut | None = None
    matches: list[DemoMatchOut] = Field(default_factory=list)


class GoldenCircuit(BaseModel):
    """A stored, verified circuit for a built-in exercise (the demo circuit)."""

    task_id: str
    title: str
    source: str  # "reference" (built by app.tools.build_golden) or "recorded" (a saved AI answer)
    circuit: Circuit


class GateInfo(BaseModel):
    type: str
    min_inputs: int
    max_inputs: int | None
    default_inputs: int
    description: str
