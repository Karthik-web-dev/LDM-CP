"""Logical equivalence by exhaustive truth-table comparison.

Two functions are equivalent iff they agree on every assignment of the union of their variables.
Expression strings are never compared.
"""

from dataclasses import dataclass

from app.analysis.boolean_ast import BooleanExpression, variables_of
from app.analysis.truth_table import generate_truth_table
from app.models.analysis import Counterexample, TruthTable


@dataclass
class ColumnComparison:
    equivalent: bool
    mismatch_count: int
    counterexamples: list[Counterexample]


def compare_columns(
    actual: TruthTable,
    actual_output: str,
    expected: TruthTable,
    expected_output: str,
    max_counterexamples: int = 8,
) -> ColumnComparison:
    """Compare one output column of two truth tables built over the same variables in the same order.

    Rows where the expected value is None (a don't-care) always match.
    """
    if actual.variables != expected.variables:
        raise ValueError("Truth tables must share the same variables in the same order")
    a_col = actual.outputs.index(actual_output)
    e_col = expected.outputs.index(expected_output)
    mismatches = 0
    examples: list[Counterexample] = []
    for a_row, e_row in zip(actual.rows, expected.rows, strict=True):
        expected_value = e_row.outputs[e_col]
        if expected_value is not None and a_row.outputs[a_col] != expected_value:
            mismatches += 1
            if len(examples) < max_counterexamples:
                examples.append(
                    Counterexample(
                        inputs=dict(zip(actual.variables, a_row.inputs)),
                        expected=e_row.outputs[e_col],
                        actual=a_row.outputs[a_col],
                    )
                )
    return ColumnComparison(mismatches == 0, mismatches, examples)


def are_equivalent(a: BooleanExpression, b: BooleanExpression, max_variables: int = 16) -> bool:
    variables = sorted(variables_of(a) | variables_of(b))
    table = generate_truth_table({"a": a, "b": b}, variables, max_variables)
    return all(row.outputs[0] == row.outputs[1] for row in table.rows)


@dataclass
class OutputMapping:
    expected_output: str
    circuit_output: str | None  # circuit output label, or None if the circuit lacks it
    label_mismatch: bool = False


def map_outputs(expected_outputs: list[str], circuit_outputs: list[str]) -> tuple[list[OutputMapping], list[str]]:
    """Pair each expected output with a circuit output label.

    Outputs are matched by label. As a convenience, a single expected output is paired with a
    single circuit output regardless of label. Returns the mapping and unmatched circuit outputs.
    """
    if len(expected_outputs) == 1 and len(circuit_outputs) == 1:
        e, c = expected_outputs[0], circuit_outputs[0]
        return [OutputMapping(e, c, label_mismatch=e != c)], []
    mappings = [OutputMapping(e, e if e in circuit_outputs else None) for e in expected_outputs]
    extra = [c for c in circuit_outputs if c not in expected_outputs]
    return mappings, extra
