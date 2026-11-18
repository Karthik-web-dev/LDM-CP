"""Automatic placement of a circuit on the editor canvas.

Parts are arranged in columns by signal depth (inputs and constants on the left, outputs on the
right), and sorted inside each column by the average height of their drivers to reduce crossings.
Sizes mirror ``componentSize`` in the frontend so nothing overlaps. Feedback wires of counters run
right to left, which is fine: they are still wired correctly.

When improving an existing circuit, ``keep`` holds the positions the student already has: those parts
stay exactly where they are and only new parts are placed, in a column to the right of them.
"""

from typing import Any

from app.analysis.gates import get_gate_definition
from app.analysis.graph import NodeKind, build_graph
from app.analysis.topological_sort import CycleDetectedError, topological_sort
from app.models.circuit import Circuit

PIN_SPACING = 20
COLUMN_GAP = 90
ROW_GAP = 30
LEFT = 40
TOP = 40


def _size(kind: str, gate: dict[str, Any] | None) -> tuple[int, int]:
    if kind != "gate" or gate is None:
        return 64, 32
    definition = get_gate_definition(gate["type"])
    if definition is not None and gate["type"].upper() in ("VCC", "GND"):
        return 40, 40
    pins = max(gate.get("inputs") or (definition.default_inputs if definition else 2), definition.n_outputs if definition else 1)
    is_block = definition is not None and (definition.build_outputs is not None or definition.sequential is not None)
    if is_block:
        return 96, pins * PIN_SPACING + 36
    return 70, max(40, pins * PIN_SPACING + 10)


def positions_of(circuit: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Positions already present in a circuit's JSON, by component id."""
    found: dict[str, tuple[float, float]] = {}
    for key in ("inputs", "gates", "outputs"):
        for item in circuit.get(key, []):
            pos = item.get("position")
            if pos:
                found[item["id"]] = (pos["x"], pos["y"])
    return found


def apply_layout(circuit: dict[str, Any], keep: dict[str, tuple[float, float]] | None = None) -> dict[str, Any]:
    """Return a copy of the normalized circuit JSON with a ``position`` on every component."""
    model = Circuit.model_validate(circuit)
    graph = build_graph(model)
    try:
        order = topological_sort(graph)
    except CycleDetectedError:
        order = list(graph.nodes)
    rank = {node_id: i for i, node_id in enumerate(order)}

    depth: dict[str, int] = {}
    for node_id in order:
        node = graph.nodes[node_id]
        if node.kind == NodeKind.INPUT or (node.kind == NodeKind.GATE and node.pin_count == 0):
            depth[node_id] = 0
            continue
        earlier = [p for p in graph.predecessors(node_id) if rank.get(p, 10**9) < rank[node_id] and p in depth]
        depth[node_id] = 1 + max((depth[p] for p in earlier), default=0)
    last = max((d for n, d in depth.items() if graph.nodes[n].kind != NodeKind.OUTPUT), default=0)
    for node_id, node in graph.nodes.items():
        if node.kind == NodeKind.OUTPUT:
            depth[node_id] = last + 1

    gates_by_id = {g["id"]: g for g in circuit["gates"]}
    sizes = {
        node_id: _size(node.kind.value, gates_by_id.get(node_id)) for node_id, node in graph.nodes.items()
    }

    columns: dict[int, list[str]] = {}
    for node_id in graph.nodes:
        columns.setdefault(depth[node_id], []).append(node_id)

    positions: dict[str, tuple[float, float]] = {}
    x = LEFT
    for d in sorted(columns):
        nodes = columns[d]
        center: dict[str, float] = {}
        for node_id in nodes:
            ys = [positions[p][1] + sizes[p][1] / 2 for p in graph.predecessors(node_id) if p in positions]
            center[node_id] = sum(ys) / len(ys) if ys else rank.get(node_id, 0) * 10**-3
        nodes.sort(key=lambda n: (center[n], rank.get(n, 0)))
        y = TOP
        for node_id in nodes:
            positions[node_id] = (x, y)
            y += sizes[node_id][1] + ROW_GAP
        x += max(sizes[n][0] for n in nodes) + COLUMN_GAP

    kept = {n: keep[n] for n in graph.nodes if keep and n in keep}
    if kept:
        # Existing parts stay put; new parts go in one column to the right of everything that was kept.
        new_x = max(kept[n][0] + sizes[n][0] for n in kept) + COLUMN_GAP
        y = TOP
        for node_id in sorted((n for n in graph.nodes if n not in kept), key=lambda n: (depth[n], positions[n][1])):
            positions[node_id] = (new_x, y)
            y += sizes[node_id][1] + ROW_GAP
        positions.update(kept)

    def snap(v: float) -> int:
        return int(round(v / 10) * 10)

    placed = {**circuit}
    for key in ("inputs", "gates", "outputs"):
        placed[key] = [
            {**item, "position": {"x": snap(positions[item["id"]][0]), "y": snap(positions[item["id"]][1])}}
            for item in circuit[key]
        ]
    return placed
