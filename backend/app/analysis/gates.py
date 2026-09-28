"""Central gate registry: arity rules and Boolean semantics for every supported gate type.

To add a gate, add one ``GateDefinition`` here (plus an AST operator in ``boolean_ast`` if it
needs a new one). Nothing else in the analysis pipeline is gate-specific.
"""

from dataclasses import dataclass
from typing import Callable

from app.analysis.boolean_ast import And, BooleanExpression, Nand, Nor, Not, Or, Xnor, Xor


@dataclass(frozen=True)
class GateDefinition:
    type: str
    min_inputs: int
    max_inputs: int | None
    default_inputs: int
    build: Callable[[list[BooleanExpression]], BooleanExpression]
    description: str

    def accepts(self, n: int) -> bool:
        return n >= self.min_inputs and (self.max_inputs is None or n <= self.max_inputs)

    def arity_text(self) -> str:
        if self.max_inputs == self.min_inputs:
            return f"exactly {self.min_inputs}"
        if self.max_inputs is None:
            return f"at least {self.min_inputs}"
        return f"between {self.min_inputs} and {self.max_inputs}"


def _nary(op: type) -> Callable[[list[BooleanExpression]], BooleanExpression]:
    return lambda args: op(tuple(args))


GATE_DEFINITIONS: dict[str, GateDefinition] = {
    d.type: d
    for d in [
        GateDefinition("AND", 2, None, 2, _nary(And), "Outputs 1 only when all inputs are 1."),
        GateDefinition("OR", 2, None, 2, _nary(Or), "Outputs 1 when at least one input is 1."),
        GateDefinition("NOT", 1, 1, 1, lambda a: Not(a[0]), "Outputs the inverse of its input."),
        GateDefinition("NAND", 2, None, 2, _nary(Nand), "Outputs 0 only when all inputs are 1."),
        GateDefinition("NOR", 2, None, 2, _nary(Nor), "Outputs 1 only when all inputs are 0."),
        GateDefinition("XOR", 2, None, 2, _nary(Xor), "Outputs 1 when an odd number of inputs are 1."),
        GateDefinition("XNOR", 2, None, 2, _nary(Xnor), "Outputs 1 when an even number of inputs are 1."),
        # A buffer passes its input through unchanged, so it adds no node to the expression.
        GateDefinition("BUFFER", 1, 1, 1, lambda a: a[0], "Outputs its input unchanged."),
    ]
}

GATE_ALIASES = {"INV": "NOT", "INVERTER": "NOT", "BUF": "BUFFER"}


def normalize_gate_type(gate_type: str) -> str:
    t = gate_type.strip().upper()
    return GATE_ALIASES.get(t, t)


def get_gate_definition(gate_type: str) -> GateDefinition | None:
    return GATE_DEFINITIONS.get(normalize_gate_type(gate_type))
