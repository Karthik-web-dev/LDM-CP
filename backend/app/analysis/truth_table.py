"""Truth-table generation."""

from itertools import product
from typing import Iterator

from app.analysis.boolean_ast import BooleanExpression
from app.analysis.evaluator import evaluate
from app.models.analysis import TruthTable, TruthTableRow


class TooManyVariablesError(ValueError):
    pass


def assignments(variables: list[str]) -> Iterator[dict[str, bool]]:
    """All 2^n assignments in binary counting order (first variable is the most significant bit)."""
    for bits in product((False, True), repeat=len(variables)):
        yield dict(zip(variables, bits))


def generate_truth_table(
    expressions: dict[str, BooleanExpression],
    variables: list[str],
    max_variables: int,
) -> TruthTable:
    """Evaluate each named expression over every assignment of ``variables``.

    ``variables`` must include every variable used by the expressions; it may include more
    (an expression simply ignores variables it does not use).
    """
    if len(variables) > max_variables:
        raise TooManyVariablesError(
            f"{len(variables)} input variables need {2 ** len(variables)} truth-table rows; the maximum is {max_variables} variables."
        )
    names = list(expressions)
    rows = []
    for env in assignments(variables):
        memo: dict[int, bool] = {}  # shared across outputs: they may share sub-expressions
        rows.append(
            TruthTableRow(
                inputs=[int(env[v]) for v in variables],
                outputs=[int(evaluate(expressions[n], env, memo)) for n in names],
            )
        )
    return TruthTable(variables=list(variables), outputs=names, rows=rows)
