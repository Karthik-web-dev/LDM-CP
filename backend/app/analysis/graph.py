"""Directed-graph view of a circuit.

Nodes are circuit inputs, gates, and outputs. Each connection becomes an edge into a specific
input pin of its target, so pin order is preserved (``gate_1`` pin 0 != ``gate_1`` pin 1).

``build_graph`` is tolerant: connections that reference unknown ids or invalid pins are skipped
and reported in ``CircuitGraph.rejected`` so the structural validator can describe them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from app.analysis.gates import get_gate_definition, normalize_gate_type
from app.models.circuit import Circuit


class NodeKind(str, Enum):
    INPUT = "input"
    GATE = "gate"
    OUTPUT = "output"


@dataclass
class Node:
    id: str
    kind: NodeKind
    order: int  # position in the source document; used only for deterministic tie-breaking
    label: str | None = None
    gate_type: str | None = None  # normalized, e.g. "AND"
    pin_count: int = 0  # number of input pins (0 for circuit inputs, 1 for outputs)


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    pin: int


@dataclass
class RejectedConnection:
    index: int
    source: str
    target: str
    reason: str
    component: str | None


@dataclass
class CircuitGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    rejected: list[RejectedConnection] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    _pin_drivers: dict[str, dict[int, list[str]]] = field(default_factory=dict)
    _successors: dict[str, list[str]] = field(default_factory=dict)

    def pin_drivers(self, node_id: str) -> dict[int, list[str]]:
        """Map of pin index -> ids of nodes driving that pin."""
        return self._pin_drivers.get(node_id, {})

    def successors(self, node_id: str) -> list[str]:
        return self._successors.get(node_id, [])

    def predecessors(self, node_id: str) -> list[str]:
        return [src for pin in sorted(self.pin_drivers(node_id)) for src in self.pin_drivers(node_id)[pin]]

    def nodes_of_kind(self, kind: NodeKind) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind == kind]

    def ancestors_of(self, node_ids: list[str]) -> set[str]:
        """All nodes with a path to any of ``node_ids`` (inclusive)."""
        seen: set[str] = set()
        stack = list(node_ids)
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            stack.extend(self.predecessors(nid))
        return seen


def build_graph(circuit: Circuit) -> CircuitGraph:
    graph = CircuitGraph()
    order = 0

    def add(node: Node) -> None:
        if node.id in graph.nodes:
            graph.duplicate_ids.append(node.id)
            return
        graph.nodes[node.id] = node

    for inp in circuit.inputs:
        add(Node(id=inp.id, kind=NodeKind.INPUT, order=order, label=inp.label))
        order += 1
    # For gates of unknown type without a declared pin count, size them from their connections
    # so the only error reported is the unknown type itself.
    used_pins: dict[str, int] = defaultdict(int)
    for conn in circuit.connections:
        used_pins[conn.to] = max(used_pins[conn.to], (conn.input_index or 0) + 1)

    for gate in circuit.gates:
        definition = get_gate_definition(gate.type)
        if gate.inputs is not None:
            pin_count = gate.inputs
        elif definition is not None:
            pin_count = definition.default_inputs
        else:
            pin_count = max(used_pins[gate.id], 1)
        add(
            Node(
                id=gate.id,
                kind=NodeKind.GATE,
                order=order,
                gate_type=normalize_gate_type(gate.type),
                pin_count=pin_count,
            )
        )
        order += 1
    for out in circuit.outputs:
        add(Node(id=out.id, kind=NodeKind.OUTPUT, order=order, label=out.label, pin_count=1))
        order += 1

    pin_drivers: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    successors: dict[str, list[str]] = defaultdict(list)

    for index, conn in enumerate(circuit.connections):
        src, dst = graph.nodes.get(conn.from_), graph.nodes.get(conn.to)

        def reject(reason: str, component: str | None) -> None:
            graph.rejected.append(RejectedConnection(index, conn.from_, conn.to, reason, component))

        if src is None:
            reject(f"source '{conn.from_}' does not exist", conn.to if dst else None)
            continue
        if dst is None:
            reject(f"target '{conn.to}' does not exist", conn.from_)
            continue
        if src.kind == NodeKind.OUTPUT:
            reject(f"output '{src.id}' cannot drive other components", src.id)
            continue
        if dst.kind == NodeKind.INPUT:
            reject(f"circuit input '{dst.id}' cannot be driven by another component", dst.id)
            continue

        pin = conn.input_index
        if pin is None:
            if dst.pin_count == 1:
                pin = 0
            else:
                reject(f"connection to '{dst.id}' must specify input_index (it has {dst.pin_count} inputs)", dst.id)
                continue
        if pin >= dst.pin_count:
            reject(f"input_index {pin} is out of range for '{dst.id}' (it has {dst.pin_count} inputs)", dst.id)
            continue

        graph.edges.append(Edge(src.id, dst.id, pin))
        pin_drivers[dst.id][pin].append(src.id)
        if dst.id not in successors[src.id]:
            successors[src.id].append(dst.id)

    graph._pin_drivers = {k: dict(v) for k, v in pin_drivers.items()}
    graph._successors = dict(successors)
    return graph
