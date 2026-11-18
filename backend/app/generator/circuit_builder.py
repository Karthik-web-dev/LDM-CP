"""Build normalized circuit JSON programmatically.

Two helpers share one output format (see CIRCUIT_FORMAT.md):

* ``NetBuilder``: wire a netlist explicitly, part by part (used for IC-based reference circuits).
* ``circuit_from_expressions``: turn Boolean expressions into a gate-level circuit, sharing identical
  sub-expressions and inverters.

Ids follow the editor's convention (``input_1``, ``gate_3``, ``output_2``) so a circuit loaded into
the editor keeps numbering consistently when more parts are added.
"""

from typing import Any

from app.analysis.boolean_ast import BooleanExpression, Const, NaryOp, Not, Variable


class NetBuilder:
    def __init__(self) -> None:
        self.inputs: list[dict[str, Any]] = []
        self.gates: list[dict[str, Any]] = []
        self.outputs: list[dict[str, Any]] = []
        self.connections: list[dict[str, Any]] = []
        self._constants: dict[str, str] = {}

    def add_input(self, label: str) -> str:
        node_id = f"input_{len(self.inputs) + 1}"
        self.inputs.append({"id": node_id, "label": label})
        return node_id

    def add_gate(self, type_: str, inputs: int) -> str:
        node_id = f"gate_{len(self.gates) + 1}"
        self.gates.append({"id": node_id, "type": type_, "inputs": inputs})
        return node_id

    def constant(self, high: bool) -> str:
        """One shared VCC or GND part."""
        kind = "VCC" if high else "GND"
        if kind not in self._constants:
            self._constants[kind] = self.add_gate(kind, 0)
        return self._constants[kind]

    def wire(self, src: str, dst: str, pin: int | None = None, out: int | None = None) -> None:
        conn: dict[str, Any] = {"from": src, "to": dst}
        if pin is not None:
            conn["input_index"] = pin
        if out:
            conn["output_index"] = out
        self.connections.append(conn)

    def wire_pins(self, src: str, dst: str, pins: list[int], out: int | None = None) -> None:
        for pin in pins:
            self.wire(src, dst, pin, out)

    def add_output(self, label: str, src: str, out: int | None = None) -> str:
        node_id = f"output_{len(self.outputs) + 1}"
        self.outputs.append({"id": node_id, "label": label})
        self.wire(src, node_id, None, out)
        return node_id

    def build(self) -> dict[str, Any]:
        return {
            "version": 1,
            "inputs": self.inputs,
            "gates": self.gates,
            "outputs": self.outputs,
            "connections": self.connections,
        }


def circuit_from_expressions(inputs: list[str], outputs: dict[str, BooleanExpression]) -> dict[str, Any]:
    """Gate-level circuit computing every expression in ``outputs`` (label -> expression)."""
    net = NetBuilder()
    input_ids = {label: net.add_input(label) for label in inputs}
    cache: dict[tuple, str] = {}

    def build(expr: BooleanExpression) -> str:
        if isinstance(expr, Variable):
            if expr.name not in input_ids:
                raise ValueError(f"The expression uses '{expr.name}', which is not an input")
            return input_ids[expr.name]
        if isinstance(expr, Const):
            return net.constant(expr.value)
        if isinstance(expr, Not):
            child = build(expr.operand)
            key = ("NOT", child)
            if key not in cache:
                cache[key] = net.add_gate("NOT", 1)
                net.wire(child, cache[key], 0)
            return cache[key]
        if isinstance(expr, NaryOp):
            children = [build(o) for o in expr.operands]
            if len(children) == 1:
                return children[0]
            key = (expr.symbol, tuple(children))
            if key not in cache:
                gate = net.add_gate(expr.symbol, len(children))
                cache[key] = gate
                for pin, child in enumerate(children):
                    net.wire(child, gate, pin)
            return cache[key]
        raise TypeError(f"Unsupported expression node {type(expr).__name__}")

    for label, expr in outputs.items():
        net.add_output(label, build(expr))
    return net.build()
