"""Result models produced by the deterministic analysis pipeline."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class IssueType(str, Enum):
    MISSING_INPUT = "MISSING_INPUT"  # a gate input pin has no driver
    MISSING_OUTPUT = "MISSING_OUTPUT"  # the circuit has no output component
    UNDRIVEN_OUTPUT = "UNDRIVEN_OUTPUT"  # an output component has no driver
    DANGLING_GATE = "DANGLING_GATE"  # gate does not contribute to any output
    UNKNOWN_GATE = "UNKNOWN_GATE"
    MULTIPLE_DRIVER = "MULTIPLE_DRIVER"
    CYCLE_DETECTED = "CYCLE_DETECTED"
    INVALID_CONNECTION = "INVALID_CONNECTION"
    INVALID_GATE_ARITY = "INVALID_GATE_ARITY"
    UNCONNECTED_INPUT = "UNCONNECTED_INPUT"  # a circuit input drives nothing
    DUPLICATE_ID = "DUPLICATE_ID"
    DUPLICATE_LABEL = "DUPLICATE_LABEL"
    INVALID_LABEL = "INVALID_LABEL"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    EXPRESSION_TOO_LARGE = "EXPRESSION_TOO_LARGE"
    OUTPUT_LABEL_MISMATCH = "OUTPUT_LABEL_MISMATCH"
    MISSING_EXPECTED_OUTPUT = "MISSING_EXPECTED_OUTPUT"
    EXTRA_OUTPUT = "EXTRA_OUTPUT"
    MISSING_TASK_INPUT = "MISSING_TASK_INPUT"
    EXTRA_INPUT = "EXTRA_INPUT"
    INVALID_TASK = "INVALID_TASK"


Severity = Literal["error", "warning"]


class StructuralIssue(BaseModel):
    type: IssueType
    severity: Severity
    component: str | None = None
    message: str
    # Other components involved, e.g. the nodes on a cycle or the competing drivers.
    related: list[str] = Field(default_factory=list)


class TruthTable(BaseModel):
    variables: list[str]
    outputs: list[str]
    # rows[i] = (input values in `variables` order, output values in `outputs` order).
    # Rows are in binary counting order with the first variable as the most significant bit.
    rows: list["TruthTableRow"]


class TruthTableRow(BaseModel):
    inputs: list[int]
    # None marks a don't-care in an expected (target) table. Circuit tables never contain None.
    outputs: list[int | None]


class Counterexample(BaseModel):
    inputs: dict[str, int]
    expected: int
    actual: int


class OutputComparison(BaseModel):
    expected_output: str
    circuit_output: str | None
    # For truth-table targets this is a simplified equation derived from the table.
    expected_expression: str
    expected_defined_by: Literal["expression", "truth_table"] = "expression"
    circuit_expression: str | None
    equivalent: bool
    counterexamples: list[Counterexample] = Field(default_factory=list)
    mismatch_count: int = 0


class DeterministicResult(BaseModel):
    structurally_valid: bool
    # Expression of the first (or only) output; convenience for single-output tasks.
    expression: str | None = None
    output_expressions: dict[str, str | None] = Field(default_factory=dict)
    variables: list[str] = Field(default_factory=list)
    truth_table: TruthTable | None = None
    expected_truth_table: TruthTable | None = None
    equivalent_to_expected: bool = False
    comparisons: list[OutputComparison] = Field(default_factory=list)
    evaluation_order: list[str] = Field(default_factory=list)
    errors: list[StructuralIssue] = Field(default_factory=list)
    warnings: list[StructuralIssue] = Field(default_factory=list)


class KMapCell(BaseModel):
    row: int
    col: int
    minterm: int  # truth-table row index
    value: int | None  # None = don't care


class KMapGroup(BaseModel):
    term: str  # textbook form, e.g. "A'B"
    expression: str  # e.g. "((NOT A) AND B)"
    minterms: list[int]
    cells: list[list[int]]  # [row, col] pairs


class KMap(BaseModel):
    output: str
    variables: list[str]
    row_variables: list[str]
    col_variables: list[str]
    row_labels: list[str]  # Gray-code bit strings
    col_labels: list[str]
    cells: list[list[KMapCell]]  # row-major
    groups: list[KMapGroup]
    minimal_sop: str
    minterms: list[int]
    dont_cares: list[int]
