"""Graph -> Boolean AST, evaluated in topological order so every driver is built before its sinks."""

from app.analysis.boolean_ast import BooleanExpression, Variable
from app.analysis.gates import get_gate_definition
from app.analysis.graph import CircuitGraph, NodeKind


class ExpressionGenerationError(Exception):
    pass


def generate_expressions(graph: CircuitGraph, order: list[str]) -> dict[str, BooleanExpression]:
    """Build an expression for every output, keyed by output id.

    Requires a structurally valid graph and its topological ``order``. Only nodes that feed an
    output are visited, so dangling gates are ignored. Shared sub-circuits produce shared AST nodes.
    """
    outputs = [n.id for n in graph.nodes_of_kind(NodeKind.OUTPUT)]
    relevant = graph.ancestors_of(outputs)
    built: dict[str, BooleanExpression] = {}

    for node_id in order:
        if node_id not in relevant:
            continue
        node = graph.nodes[node_id]
        if node.kind == NodeKind.INPUT:
            built[node_id] = Variable(node.label or node_id)
            continue

        drivers = graph.pin_drivers(node_id)
        operands: list[BooleanExpression] = []
        for pin in range(node.pin_count):
            sources = drivers.get(pin, [])
            if len(sources) != 1 or sources[0] not in built:
                raise ExpressionGenerationError(f"Pin {pin} of {node_id} has no single evaluated driver")
            operands.append(built[sources[0]])

        if node.kind == NodeKind.OUTPUT:
            built[node_id] = operands[0]
        else:
            definition = get_gate_definition(node.gate_type or "")
            if definition is None:
                raise ExpressionGenerationError(f"Unknown gate type {node.gate_type!r} on {node_id}")
            built[node_id] = definition.build(operands)

    return {oid: built[oid] for oid in outputs}
