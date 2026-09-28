"""What the student is asked to build: an equation or a truth table."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.analysis.expression_parser import is_valid_identifier

# Largest truth-table target accepted (2^10 = 1024 rows per output).
MAX_TABLE_INPUTS = 10

TruthValue = Literal[0, 1, "X"]


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)
    # Exactly one of the three definitions below must be given.
    # 1. Single-output equation. Equivalent to expected_outputs={outputs[0] or "Y": expected_expression}.
    expected_expression: str | None = Field(default=None, max_length=1000)
    # 2. Output label -> equation, for multi-output tasks.
    expected_outputs: dict[str, str] | None = None
    # 3. Output label -> output column over `inputs`, in binary counting order (first input is the
    #    most significant bit). "X" (also accepted: "x", "-", null) marks a don't-care row.
    expected_truth_table: dict[str, list[TruthValue]] | None = None
    # Input labels in the order truth tables list them. Required for truth-table tasks.
    inputs: list[str] = Field(default_factory=list, max_length=16)
    outputs: list[str] = Field(default_factory=list, max_length=16)
    hint: str | None = Field(default=None, max_length=1000)

    @field_validator("expected_truth_table", mode="before")
    @classmethod
    def _normalize_cells(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = {}
        for label, column in value.items():
            if not isinstance(column, list):
                normalized[label] = column
                continue
            normalized[label] = [
                "X" if c is None or (isinstance(c, str) and c.strip().upper() in {"X", "-"})
                else int(c) if isinstance(c, str) and c.strip() in {"0", "1"}
                else c
                for c in column
            ]
        return normalized

    @model_validator(mode="after")
    def _check_expected(self) -> "Task":
        given = [x is not None and x != "" for x in (self.expected_expression, self.expected_outputs, self.expected_truth_table)]
        if sum(given) != 1:
            raise ValueError("Define the target with exactly one of expected_expression, expected_outputs or expected_truth_table")

        if self.expected_outputs is not None:
            if not self.expected_outputs or len(self.expected_outputs) > 16:
                raise ValueError("expected_outputs must have between 1 and 16 entries")
            if any(len(e) > 1000 for e in self.expected_outputs.values()):
                raise ValueError("expected expressions are limited to 1000 characters")

        if self.expected_truth_table is not None:
            if not self.inputs:
                raise ValueError("A truth-table task must list its inputs")
            if len(self.inputs) > MAX_TABLE_INPUTS:
                raise ValueError(f"A truth-table task can have at most {MAX_TABLE_INPUTS} inputs")
            if len(set(self.inputs)) != len(self.inputs):
                raise ValueError("Input names must be unique")
            if not self.expected_truth_table or len(self.expected_truth_table) > 16:
                raise ValueError("expected_truth_table must have between 1 and 16 outputs")
            rows = 2 ** len(self.inputs)
            for label, column in self.expected_truth_table.items():
                if len(column) != rows:
                    raise ValueError(f"Output {label} needs {rows} values (one per row for {len(self.inputs)} inputs), got {len(column)}")

        labels = list(self.inputs) + list(self.outputs) + list(self.expected_outputs or {}) + list(self.expected_truth_table or {})
        for name in labels:
            if not is_valid_identifier(name) or len(name) > 32:
                raise ValueError(f"'{name[:32]}' is not a valid name. Use letters, digits and _ (starting with a letter), and not an operator name")
        return self

    def output_labels(self) -> list[str]:
        if self.expected_truth_table is not None:
            return list(self.expected_truth_table)
        return list(self.resolved_expected_outputs())

    def resolved_expected_outputs(self) -> dict[str, str]:
        """Equation targets only: output label -> expression text."""
        if self.expected_outputs:
            return dict(self.expected_outputs)
        if self.expected_expression:
            label = self.outputs[0] if self.outputs else "Y"
            return {label: self.expected_expression}
        return {}
