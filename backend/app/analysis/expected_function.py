"""The function a circuit is validated against, defined either by an equation or by a truth table.

Both forms become ``ExpectedOutput`` objects that can be evaluated for any assignment. A
truth-table target may contain don't-cares ("X"); those rows evaluate to None and are skipped
when comparing.
"""

from dataclasses import dataclass
from itertools import product
from typing import Literal

from app.analysis.boolean_ast import BooleanExpression, render_expression, variables_of
from app.analysis.evaluator import evaluate
from app.analysis.expression_parser import ExpressionParseError, parse_expression
from app.analysis.minimize import minimize_sop
from app.models.analysis import TruthTable, TruthTableRow
from app.models.task import Task


@dataclass
class ExpectedOutput:
    label: str
    defined_by: Literal["expression", "truth_table"]
    # Equation as typed (expression targets) or a simplified equation derived from the table.
    display: str
    expression: BooleanExpression  # parsed equation, or simplified SOP for tables (don't-cares resolved)
    variables: list[str]  # variables the definition refers to
    # Truth-table targets: value per row over ``variables`` in binary counting order; None = don't care.
    table: list[bool | None] | None = None

    def evaluate(self, env: dict[str, bool]) -> bool | None:
        if self.table is None:
            return evaluate(self.expression, env)
        index = 0
        for name in self.variables:
            index = (index << 1) | int(env[name])
        return self.table[index]


class ExpectedFunctionError(ValueError):
    pass


def build_expected(task: Task) -> tuple[list[ExpectedOutput], list[str]]:
    """Return the expected outputs and a list of human-readable problems with the task."""
    outputs: list[ExpectedOutput] = []
    problems: list[str] = []

    if task.expected_truth_table is not None:
        variables = list(task.inputs)
        for label, values in task.expected_truth_table.items():
            table = [None if v == "X" else bool(v) for v in values]
            ones = {i for i, v in enumerate(table) if v is True}
            dont_cares = {i for i, v in enumerate(table) if v is None}
            sop = minimize_sop(variables, ones, dont_cares)
            outputs.append(ExpectedOutput(label, "truth_table", render_expression(sop), sop, variables, table))
        return outputs, problems

    for label, source in task.resolved_expected_outputs().items():
        try:
            expr = parse_expression(source, known_variables=task.inputs)
        except ExpressionParseError as exc:
            problems.append(f"The expected expression for {label} could not be parsed: {exc}")
            continue
        outputs.append(ExpectedOutput(label, "expression", source, expr, sorted(variables_of(expr))))
    return outputs, problems


def expected_truth_table(outputs: list[ExpectedOutput], variables: list[str], max_variables: int) -> TruthTable:
    """Evaluate expected outputs over ``variables`` (a superset of each output's variables)."""
    if len(variables) > max_variables:
        raise ExpectedFunctionError(f"{len(variables)} variables exceed the limit of {max_variables}")
    rows = []
    for bits in product((False, True), repeat=len(variables)):
        env = dict(zip(variables, bits))
        values = [o.evaluate(env) for o in outputs]
        rows.append(TruthTableRow(inputs=[int(b) for b in bits], outputs=[None if v is None else int(v) for v in values]))
    return TruthTable(variables=list(variables), outputs=[o.label for o in outputs], rows=rows)
