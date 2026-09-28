"""Structural validation: everything that must hold before Boolean analysis is meaningful."""

from collections import Counter
from dataclasses import dataclass, field

from app.analysis.expression_parser import is_valid_identifier
from app.analysis.gates import get_gate_definition
from app.analysis.graph import CircuitGraph, NodeKind, build_graph
from app.analysis.topological_sort import CycleDetectedError, topological_sort
from app.config import Limits
from app.models.analysis import IssueType, Severity, StructuralIssue
from app.models.circuit import Circuit


@dataclass
class StructuralReport:
    graph: CircuitGraph | None
    issues: list[StructuralIssue] = field(default_factory=list)
    # Topological order of all nodes; None if the graph has a cycle or was not built.
    order: list[str] | None = None

    @property
    def errors(self) -> list[StructuralIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[StructuralIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def has_errors(self) -> bool:
        return bool(self.errors)


def check_limits(circuit: Circuit, limits: Limits) -> list[StructuralIssue]:
    checks = [
        ("inputs", len(circuit.inputs), limits.max_inputs),
        ("gates", len(circuit.gates), limits.max_gates),
        ("outputs", len(circuit.outputs), limits.max_outputs),
        ("connections", len(circuit.connections), limits.max_connections),
    ]
    return [
        StructuralIssue(
            type=IssueType.LIMIT_EXCEEDED,
            severity="error",
            message=f"The circuit has {count} {name}; the maximum is {maximum}.",
        )
        for name, count, maximum in checks
        if count > maximum
    ]


def validate_structure(circuit: Circuit, limits: Limits) -> StructuralReport:
    limit_issues = check_limits(circuit, limits)
    if limit_issues:
        return StructuralReport(graph=None, issues=limit_issues)

    graph = build_graph(circuit)
    issues: list[StructuralIssue] = []

    def add(type_: IssueType, severity: Severity, component: str | None, message: str, related=()) -> None:
        issues.append(StructuralIssue(type=type_, severity=severity, component=component, message=message, related=list(related)))

    for dup in dict.fromkeys(graph.duplicate_ids):
        add(IssueType.DUPLICATE_ID, "error", dup, f"More than one component uses the id '{dup}'.")

    # Labels become Boolean variable names, so they must be unique identifiers.
    for kind, items in (("input", circuit.inputs), ("output", circuit.outputs)):
        for item in items:
            if len(item.label) > limits.max_label_length or not is_valid_identifier(item.label):
                add(
                    IssueType.INVALID_LABEL, "error", item.id,
                    f"The {kind} label '{item.label[:limits.max_label_length]}' is not valid. Use a short name made of "
                    "letters, digits and underscores that starts with a letter (e.g. A, B, Y1) and is not an operator name.",
                )
        counts = Counter(item.label for item in items)
        for label, n in counts.items():
            if n > 1:
                ids = [item.id for item in items if item.label == label]
                add(IssueType.DUPLICATE_LABEL, "error", ids[0], f"{n} {kind}s share the label '{label}'.", ids)

    if not circuit.outputs:
        add(IssueType.MISSING_OUTPUT, "error", None, "The circuit has no output. Add at least one output.")

    for gate in circuit.gates:
        definition = get_gate_definition(gate.type)
        if definition is None:
            add(IssueType.UNKNOWN_GATE, "error", gate.id, f"'{gate.type}' is not a supported gate type (gate {gate.id}).")
            continue
        node = graph.nodes.get(gate.id)
        if node and not definition.accepts(node.pin_count):
            add(
                IssueType.INVALID_GATE_ARITY, "error", gate.id,
                f"{definition.type} gate {gate.id} has {node.pin_count} inputs but needs {definition.arity_text()}.",
            )

    for rej in graph.rejected:
        add(IssueType.INVALID_CONNECTION, "error", rej.component, f"Connection #{rej.index + 1} ({rej.source} -> {rej.target}) is invalid: {rej.reason}.")

    # Nodes that feed at least one output. Problems on other gates are reported as warnings,
    # because they cannot affect the circuit's function.
    output_ids = [n.id for n in graph.nodes_of_kind(NodeKind.OUTPUT)]
    contributing = graph.ancestors_of(output_ids)

    for node in graph.nodes.values():
        drivers = graph.pin_drivers(node.id)
        if node.kind == NodeKind.GATE:
            severity: Severity = "error" if node.id in contributing else "warning"
            for pin in range(node.pin_count):
                if not drivers.get(pin):
                    add(IssueType.MISSING_INPUT, severity, node.id, f"{node.gate_type} gate {node.id} has nothing connected to input {pin + 1}.")
        if node.kind == NodeKind.OUTPUT and not drivers.get(0):
            add(IssueType.UNDRIVEN_OUTPUT, "error", node.id, f"Output {node.label} ({node.id}) is not connected to anything.")
        for pin, sources in drivers.items():
            if len(sources) > 1:
                what = f"input {pin + 1} of {node.gate_type} gate {node.id}" if node.kind == NodeKind.GATE else f"output {node.label} ({node.id})"
                add(IssueType.MULTIPLE_DRIVER, "error", node.id, f"{len(sources)} signals are wired into {what}; each input can have only one source.", sources)

    for node in graph.nodes_of_kind(NodeKind.GATE):
        if node.id not in contributing:
            add(IssueType.DANGLING_GATE, "warning", node.id, f"{node.gate_type} gate {node.id} is not connected to any output, so it has no effect.")
    for node in graph.nodes_of_kind(NodeKind.INPUT):
        if not graph.successors(node.id):
            add(IssueType.UNCONNECTED_INPUT, "warning", node.id, f"Input {node.label} ({node.id}) is not connected to anything.")

    order: list[str] | None = None
    try:
        order = topological_sort(graph)
    except CycleDetectedError as exc:
        add(
            IssueType.CYCLE_DETECTED, "error", exc.cycle[0],
            "The circuit contains a feedback loop (" + " -> ".join(exc.cycle + exc.cycle[:1]) + "). "
            "Only combinational circuits (no loops) are supported.",
            exc.cycle,
        )

    return StructuralReport(graph=graph, issues=issues, order=order)
