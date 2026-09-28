"""Compact circuit builders for tests."""

from app.models.circuit import Circuit


def make_circuit(
    inputs: list[str],
    gates: dict[str, str | tuple[str, int]],
    outputs: list[str],
    wires: list[tuple],
) -> dict:
    """Build normalized circuit JSON.

    Inputs get ids ``in_<label>`` and outputs ``out_<label>``. Wires are ``(from, to)`` or
    ``(from, to, input_index)`` where endpoints are input/output labels or gate ids.
    """

    def resolve(name: str) -> str:
        if name in inputs:
            return f"in_{name}"
        if name in outputs:
            return f"out_{name}"
        return name

    gate_list = []
    for gid, spec in gates.items():
        gtype, n = (spec, None) if isinstance(spec, str) else spec
        gate = {"id": gid, "type": gtype}
        if n is not None:
            gate["inputs"] = n
        gate_list.append(gate)

    connections = []
    for wire in wires:
        conn = {"from": resolve(wire[0]), "to": resolve(wire[1])}
        if len(wire) > 2:
            conn["input_index"] = wire[2]
        connections.append(conn)

    return {
        "version": 1,
        "inputs": [{"id": f"in_{l}", "label": l} for l in inputs],
        "gates": gate_list,
        "outputs": [{"id": f"out_{l}", "label": l} for l in outputs],
        "connections": connections,
    }


def circuit(*args, **kwargs) -> Circuit:
    return Circuit.model_validate(make_circuit(*args, **kwargs))


def and_or_circuit() -> Circuit:
    """A -> AND.0, B -> AND.1, AND -> OR.0, C -> OR.1, OR -> Y  ==  ((A AND B) OR C)"""
    return circuit(
        ["A", "B", "C"],
        {"g_and": "AND", "g_or": "OR"},
        ["Y"],
        [("A", "g_and", 0), ("B", "g_and", 1), ("g_and", "g_or", 0), ("C", "g_or", 1), ("g_or", "Y")],
    )
