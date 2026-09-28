"""Evaluate a Boolean AST for one assignment of its variables."""

from app.analysis.boolean_ast import BooleanExpression, Const, NaryOp, Not, Variable


class MissingVariableError(KeyError):
    pass


def evaluate(expr: BooleanExpression, env: dict[str, bool], memo: dict[int, bool] | None = None) -> bool:
    """Evaluate ``expr`` under ``env``.

    ``memo`` caches results by node identity, so shared sub-expressions in a DAG are computed once.
    Pass a fresh dict (or None) per assignment.
    """
    if memo is None:
        memo = {}
    key = id(expr)
    if key in memo:
        return memo[key]

    if isinstance(expr, Const):
        result = expr.value
    elif isinstance(expr, Variable):
        if expr.name not in env:
            raise MissingVariableError(expr.name)
        result = env[expr.name]
    elif isinstance(expr, Not):
        result = not evaluate(expr.operand, env, memo)
    elif isinstance(expr, NaryOp):
        result = expr.combine([evaluate(o, env, memo) for o in expr.operands])
    else:
        raise TypeError(f"Unknown expression node {type(expr).__name__}")

    memo[key] = result
    return result
