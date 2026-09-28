"""Internal Boolean expression tree.

Nodes are immutable. Equality is by identity (``eq=False``): expressions generated from a circuit
form a DAG with shared sub-expressions, and structural hashing would be exponential on them.
Use truth tables (see ``equivalence``) to compare expressions.

To add an operator: subclass ``NaryOp`` with a ``symbol`` and a ``combine`` function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Iterator


class BooleanExpression:
    def children(self) -> tuple[BooleanExpression, ...]:
        return ()


@dataclass(frozen=True, eq=False)
class Const(BooleanExpression):
    value: bool


@dataclass(frozen=True, eq=False)
class Variable(BooleanExpression):
    name: str


@dataclass(frozen=True, eq=False)
class Not(BooleanExpression):
    operand: BooleanExpression

    def children(self) -> tuple[BooleanExpression, ...]:
        return (self.operand,)


@dataclass(frozen=True, eq=False)
class NaryOp(BooleanExpression):
    operands: tuple[BooleanExpression, ...]

    symbol: ClassVar[str]

    def __post_init__(self) -> None:
        if len(self.operands) < 1:
            raise ValueError(f"{type(self).__name__} needs at least one operand")

    def children(self) -> tuple[BooleanExpression, ...]:
        return self.operands

    @staticmethod
    def combine(values: list[bool]) -> bool:
        raise NotImplementedError


class And(NaryOp):
    symbol = "AND"

    @staticmethod
    def combine(values: list[bool]) -> bool:
        return all(values)


class Or(NaryOp):
    symbol = "OR"

    @staticmethod
    def combine(values: list[bool]) -> bool:
        return any(values)


class Xor(NaryOp):
    """N-ary XOR is odd parity, matching cascaded 2-input XOR gates."""

    symbol = "XOR"

    @staticmethod
    def combine(values: list[bool]) -> bool:
        return sum(values) % 2 == 1


class Nand(NaryOp):
    symbol = "NAND"

    @staticmethod
    def combine(values: list[bool]) -> bool:
        return not all(values)


class Nor(NaryOp):
    symbol = "NOR"

    @staticmethod
    def combine(values: list[bool]) -> bool:
        return not any(values)


class Xnor(NaryOp):
    symbol = "XNOR"

    @staticmethod
    def combine(values: list[bool]) -> bool:
        return sum(values) % 2 == 0


def iter_unique_nodes(expr: BooleanExpression) -> Iterator[BooleanExpression]:
    """Yield every distinct node (by identity) in the expression DAG once."""
    seen: set[int] = set()
    stack = [expr]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        yield node
        stack.extend(node.children())


def variables_of(expr: BooleanExpression) -> set[str]:
    return {n.name for n in iter_unique_nodes(expr) if isinstance(n, Variable)}


def rendered_length(expr: BooleanExpression) -> int:
    """Length of ``render_expression(expr)`` computed without rendering.

    Shared sub-expressions are re-rendered at every use, so the rendered string can be
    exponentially larger than the DAG. Check this before rendering.
    """
    memo: dict[int, int] = {}

    def length(node: BooleanExpression) -> int:
        key = id(node)
        if key in memo:
            return memo[key]
        if isinstance(node, Const):
            result = 1
        elif isinstance(node, Variable):
            result = len(node.name)
        elif isinstance(node, Not):
            result = len("(NOT )") + length(node.operand)
        elif isinstance(node, NaryOp):
            if len(node.operands) == 1:
                result = length(node.operands[0]) + len(node.symbol) + 3
            else:
                sep = len(node.symbol) + 2
                result = 2 + sum(length(o) for o in node.operands) + sep * (len(node.operands) - 1)
        else:
            raise TypeError(f"Unknown expression node {type(node).__name__}")
        memo[key] = result
        return result

    return length(expr)


def render_expression(expr: BooleanExpression) -> str:
    """Render fully parenthesised infix, e.g. ``((A AND B) OR C)`` or ``(NOT A)``."""
    if isinstance(expr, Const):
        return "1" if expr.value else "0"
    if isinstance(expr, Variable):
        return expr.name
    if isinstance(expr, Not):
        return f"(NOT {render_expression(expr.operand)})"
    if isinstance(expr, NaryOp):
        if len(expr.operands) == 1:
            # Degenerate single-input gate (e.g. a 1-input NAND), rendered as a function call.
            return f"{expr.symbol}({render_expression(expr.operands[0])})"
        return "(" + f" {expr.symbol} ".join(render_expression(o) for o in expr.operands) + ")"
    raise TypeError(f"Unknown expression node {type(expr).__name__}")
