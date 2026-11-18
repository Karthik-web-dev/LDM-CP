"""Simulation of circuits with memory, checked against an expected sequence.

Memory comes in two forms, and one simulator handles both:

* flip-flop ICs (7476, 7474), which sample their pins on the active clock edge;
* gate-level feedback, such as two cross-coupled NAND gates forming a latch.

Each step of a ``SequenceSpec`` sets some inputs, gives one full clock pulse (0 -> 1 -> 0) when the spec
has a clock, and then reads the outputs. Every input, flip-flop and gate output starts at 0, and gates
are evaluated in the order they appear in the circuit, so a feedback circuit always reaches the same
state. Set the state you want to test explicitly in the first steps: a latch's power-up state is not
defined by the circuit.

Flip-flops sample all their pins at the same moment, so synchronous circuits behave correctly, and a
flip-flop clocked by another flip-flop's output (a ripple counter) triggers one settling pass later,
like real hardware. A circuit that never settles (an oscillator) raises ``UnstableCircuitError``.
"""

from app.analysis.boolean_ast import Const
from app.analysis.evaluator import evaluate
from app.analysis.gates import SequentialSpec, get_gate_definition
from app.analysis.graph import CircuitGraph, Node, NodeKind
from app.models.analysis import SequenceResult, SequenceRow
from app.models.task import SequenceSpec

# Settling passes allowed per input change before giving up (a ripple chain needs about one per stage).
MAX_PASSES = 200


class UnstableCircuitError(Exception):
    """The circuit keeps changing and never settles, for example a ring oscillator."""


def _jk_next(j: bool, k: bool, q: bool) -> bool:
    if j and k:
        return not q
    if j:
        return True
    if k:
        return False
    return q


class _Simulator:
    def __init__(self, graph: CircuitGraph):
        self.graph = graph
        self.nodes = list(graph.nodes.values())  # document order: inputs, gates, outputs
        self.values: dict[tuple[str, int], bool] = {
            (n.id, pin): False for n in self.nodes for pin in range(max(n.out_count, 1))
        }
        # Flip-flops: (IC id, index inside the IC) -> stored bit, and the clock level seen last pass.
        self.stored: dict[tuple[str, int], bool] = {}
        self.last_clock: dict[tuple[str, int], bool] = {}
        self.flip_flops: list[tuple[Node, SequentialSpec]] = []
        for node in self.nodes:
            definition = get_gate_definition(node.gate_type or "") if node.kind == NodeKind.GATE else None
            if definition is not None and definition.sequential is not None:
                self.flip_flops.append((node, definition.sequential))
                for f in range(definition.sequential.ffs):
                    self.stored[(node.id, f)] = False

    def read(self, node_id: str, pin: int) -> bool:
        """Value on an input pin. An unwired pin reads 0: it can only be on a gate that feeds nothing
        (anywhere else the structural check has already reported it), and that gate cannot matter."""
        sources = self.graph.pin_sources(node_id).get(pin)
        return self.values[sources[0]] if sources else False

    def set_input(self, label: str, value: bool) -> None:
        node = next(n for n in self.graph.nodes_of_kind(NodeKind.INPUT) if n.label == label)
        self.values[(node.id, 0)] = value

    def output(self, label: str) -> bool:
        node = next(n for n in self.graph.nodes_of_kind(NodeKind.OUTPUT) if n.label == label)
        return self.values[(node.id, 0)]

    def _relax(self) -> None:
        """Evaluate every gate in circuit order, repeatedly, until no signal changes."""
        for _ in range(MAX_PASSES):
            changed = False
            for node in self.nodes:
                if node.kind == NodeKind.INPUT:
                    continue
                if node.kind == NodeKind.OUTPUT:
                    new = [self.read(node.id, 0)]
                else:
                    definition = get_gate_definition(node.gate_type or "")
                    assert definition is not None
                    if definition.sequential is not None:
                        new = []
                        for f in range(definition.sequential.ffs):
                            bit = self.stored[(node.id, f)]
                            new += [bit, not bit]  # Q, then /Q
                    else:
                        operands = [Const(self.read(node.id, pin)) for pin in range(node.pin_count)]
                        new = [evaluate(expr, {}) for expr in definition.build_all(operands)]
                for pin, value in enumerate(new):
                    if self.values[(node.id, pin)] != value:
                        self.values[(node.id, pin)] = value
                        changed = True
            if not changed:
                return
        raise UnstableCircuitError

    def _flip_flops(self, edges: bool) -> bool:
        """Update every flip-flop from the settled signals. Returns True if any stored bit changed."""
        updated = dict(self.stored)
        for node, seq in self.flip_flops:
            for f in range(seq.ffs):
                base = f * seq.stride

                def level(offset: int) -> bool:
                    return self.read(node.id, base + offset)

                key = (node.id, f)
                clock = level(seq.clk)
                before = self.last_clock.get(key)
                self.last_clock[key] = clock
                if not level(seq.clr):  # asynchronous, active low, wins over preset
                    updated[key] = False
                elif not level(seq.pre):
                    updated[key] = True
                elif edges and before is not None and ((before and not clock) if seq.edge == "falling" else (not before and clock)):
                    if seq.kind == "d":
                        updated[key] = level(seq.d)  # type: ignore[arg-type]
                    else:
                        updated[key] = _jk_next(level(seq.j), level(seq.k), self.stored[key])  # type: ignore[arg-type]
        changed = updated != self.stored
        self.stored = updated
        return changed

    def settle(self, edges: bool) -> None:
        for _ in range(MAX_PASSES):
            self._relax()
            if not self._flip_flops(edges):
                return
        raise UnstableCircuitError


def run_sequence(graph: CircuitGraph, spec: SequenceSpec) -> SequenceResult:
    sim = _Simulator(graph)
    sim.settle(edges=False)  # power-up: apply asynchronous preset/clear and record the starting clock levels

    rows: list[SequenceRow] = []
    for number, step in enumerate(spec.steps, start=1):
        for label, value in step.inputs.items():
            sim.set_input(label, bool(value))
        if spec.clock is None:
            sim.settle(edges=True)
        else:
            for level in (False, True, False):  # one full clock pulse
                sim.set_input(spec.clock, level)
                sim.settle(edges=True)
        actual = {label: int(sim.output(label)) for label in step.outputs}
        rows.append(SequenceRow(step=number, inputs=dict(step.inputs), expected=dict(step.outputs), actual=actual, ok=actual == dict(step.outputs)))

    first_bad = next((r.step for r in rows if not r.ok), None)
    return SequenceResult(clock=spec.clock, rows=rows, all_match=first_bad is None, first_mismatch=first_bad)
