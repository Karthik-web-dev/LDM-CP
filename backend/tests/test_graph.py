import pytest

from app.analysis.graph import NodeKind, build_graph
from app.analysis.topological_sort import CycleDetectedError, topological_sort
from tests.helpers import and_or_circuit, circuit


def test_graph_nodes_and_pin_order():
    g = build_graph(and_or_circuit())
    assert {n.id: n.kind for n in g.nodes.values()} == {
        "in_A": NodeKind.INPUT, "in_B": NodeKind.INPUT, "in_C": NodeKind.INPUT,
        "g_and": NodeKind.GATE, "g_or": NodeKind.GATE, "out_Y": NodeKind.OUTPUT,
    }
    assert g.pin_drivers("g_and") == {0: ["in_A"], 1: ["in_B"]}
    assert g.pin_drivers("g_or") == {0: ["g_and"], 1: ["in_C"]}
    assert g.pin_drivers("out_Y") == {0: ["g_or"]}
    assert g.successors("in_A") == ["g_and"]
    assert g.predecessors("g_or") == ["g_and", "in_C"]


def test_pin_order_is_preserved_not_connection_order():
    c = circuit(["A", "B"], {"g": "AND"}, ["Y"], [("B", "g", 1), ("A", "g", 0), ("g", "Y")])
    assert build_graph(c).pin_drivers("g") == {0: ["in_A"], 1: ["in_B"]}


def test_ancestors_traversal():
    g = build_graph(and_or_circuit())
    assert g.ancestors_of(["g_and"]) == {"g_and", "in_A", "in_B"}
    assert g.ancestors_of(["out_Y"]) == set(g.nodes)


def test_single_input_target_defaults_to_pin_zero():
    c = circuit(["A"], {"n": "NOT"}, ["Y"], [("A", "n"), ("n", "Y")])
    g = build_graph(c)
    assert g.pin_drivers("n") == {0: ["in_A"]}
    assert not g.rejected


@pytest.mark.parametrize(
    "wire, reason_fragment",
    [
        (("A", "missing_gate", 0), "does not exist"),
        (("ghost", "g", 0), "does not exist"),
        (("A", "g", 5), "out of range"),
        (("A", "g"), "must specify input_index"),
        (("Y", "g", 0), "cannot drive"),
        (("g", "A"), "cannot be driven"),
    ],
)
def test_invalid_connections_are_rejected(wire, reason_fragment):
    c = circuit(["A"], {"g": "AND"}, ["Y"], [wire])
    g = build_graph(c)
    assert len(g.rejected) == 1
    assert reason_fragment in g.rejected[0].reason
    assert not g.edges


def test_topological_order_matches_spec_example():
    g = build_graph(and_or_circuit())
    assert topological_sort(g) == ["in_A", "in_B", "in_C", "g_and", "g_or", "out_Y"]


def test_topological_order_respects_dependencies_not_document_order():
    # g2 is listed first but depends on g1.
    c = circuit(["A", "B"], {"g2": "NOT", "g1": "AND"}, ["Y"], [("A", "g1", 0), ("B", "g1", 1), ("g1", "g2"), ("g2", "Y")])
    order = topological_sort(build_graph(c))
    assert order.index("g1") < order.index("g2") < order.index("out_Y")


def test_cycle_detection_two_gates():
    c = circuit(["A"], {"gate_1": "OR", "gate_2": "NOT"}, ["Y"], [
        ("A", "gate_1", 0), ("gate_2", "gate_1", 1), ("gate_1", "gate_2"), ("gate_2", "Y"),
    ])
    with pytest.raises(CycleDetectedError) as exc:
        topological_sort(build_graph(c))
    assert set(exc.value.cycle) == {"gate_1", "gate_2"}


def test_cycle_detection_self_loop():
    c = circuit(["A"], {"g": "AND"}, ["Y"], [("A", "g", 0), ("g", "g", 1), ("g", "Y")])
    with pytest.raises(CycleDetectedError) as exc:
        topological_sort(build_graph(c))
    assert exc.value.cycle == ["g"]
