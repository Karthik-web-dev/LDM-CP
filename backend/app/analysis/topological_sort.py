"""Kahn's-algorithm topological sort with cycle detection."""

import heapq

from app.analysis.graph import CircuitGraph


class CycleDetectedError(Exception):
    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        super().__init__("Cycle detected: " + " -> ".join(cycle + cycle[:1]))


def topological_sort(graph: CircuitGraph) -> list[str]:
    """Return node ids ordered so every node comes after all of its drivers.

    Ties are broken by document order, so the result is deterministic.
    Raises ``CycleDetectedError`` (with one concrete cycle) if the graph is not acyclic.
    """
    in_degree = {nid: 0 for nid in graph.nodes}
    targets: dict[str, list[str]] = {nid: [] for nid in graph.nodes}
    for edge in graph.edges:
        in_degree[edge.target] += 1
        targets[edge.source].append(edge.target)

    ready = [(graph.nodes[nid].order, nid) for nid, deg in in_degree.items() if deg == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        _, nid = heapq.heappop(ready)
        order.append(nid)
        for target in targets[nid]:
            in_degree[target] -= 1
            if in_degree[target] == 0:
                heapq.heappush(ready, (graph.nodes[target].order, target))

    if len(order) != len(graph.nodes):
        ordered = set(order)
        remaining = {nid for nid in graph.nodes if nid not in ordered}
        raise CycleDetectedError(_find_cycle(graph, remaining))
    return order


def _find_cycle(graph: CircuitGraph, candidates: set[str]) -> list[str]:
    """Find one concrete cycle among nodes Kahn's algorithm could not order.

    Every unordered node has an unordered predecessor, so walking predecessors must revisit a node.
    """
    start = min(candidates, key=lambda n: graph.nodes[n].order)
    path: list[str] = []
    position: dict[str, int] = {}
    node = start
    while node not in position:
        position[node] = len(path)
        path.append(node)
        node = next(p for p in graph.predecessors(node) if p in candidates)
    cycle = path[position[node]:]
    cycle.reverse()  # predecessor walk -> signal-flow order
    return cycle
