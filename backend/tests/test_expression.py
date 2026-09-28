import pytest

from app.analysis.boolean_ast import And, Not, Or, Variable, render_expression, rendered_length
from app.analysis.evaluator import MissingVariableError, evaluate
from app.analysis.expression_generator import generate_expressions
from app.analysis.expression_parser import ExpressionParseError, parse_expression
from app.analysis.graph import build_graph
from app.analysis.topological_sort import topological_sort
from tests.helpers import and_or_circuit, circuit


def expressions_of(c):
    g = build_graph(c)
    exprs = generate_expressions(g, topological_sort(g))
    return {g.nodes[oid].label: render_expression(e) for oid, e in exprs.items()}


def test_render():
    a, b, c = Variable("A"), Variable("B"), Variable("C")
    assert render_expression(And((a, b))) == "(A AND B)"
    assert render_expression(Not(a)) == "(NOT A)"
    assert render_expression(Or((And((a, b)), c))) == "((A AND B) OR C)"


def test_spec_algorithm_example():
    assert expressions_of(and_or_circuit()) == {"Y": "((A AND B) OR C)"}


@pytest.mark.parametrize(
    "gate, expected",
    [
        ("AND", "(A AND B)"), ("OR", "(A OR B)"), ("NAND", "(A NAND B)"),
        ("NOR", "(A NOR B)"), ("XOR", "(A XOR B)"), ("XNOR", "(A XNOR B)"),
    ],
)
def test_two_input_gates(gate, expected):
    c = circuit(["A", "B"], {"g": gate}, ["Y"], [("A", "g", 0), ("B", "g", 1), ("g", "Y")])
    assert expressions_of(c) == {"Y": expected}


def test_not_and_buffer():
    c = circuit(["A"], {"n": "NOT", "b": "BUFFER"}, ["Y"], [("A", "b"), ("b", "n"), ("n", "Y")])
    assert expressions_of(c) == {"Y": "(NOT A)"}


def test_three_input_gate_and_pin_order():
    c = circuit(["A", "B", "C"], {"g": ("OR", 3)}, ["Y"], [("C", "g", 0), ("A", "g", 1), ("B", "g", 2), ("g", "Y")])
    assert expressions_of(c) == {"Y": "(C OR A OR B)"}


def test_nested_gates():
    # Y = NOT((A AND B) OR (NOT C))
    c = circuit(
        ["A", "B", "C"],
        {"g1": "AND", "g2": "NOT", "g3": "OR", "g4": "NOT"},
        ["Y"],
        [("A", "g1", 0), ("B", "g1", 1), ("C", "g2"), ("g1", "g3", 0), ("g2", "g3", 1), ("g3", "g4"), ("g4", "Y")],
    )
    assert expressions_of(c) == {"Y": "(NOT ((A AND B) OR (NOT C)))"}


def test_multiple_outputs_and_fanout():
    c = circuit(
        ["A", "B", "C"], {"g1": "AND", "g2": "OR"}, ["Y1", "Y2"],
        [("A", "g1", 0), ("B", "g1", 1), ("A", "g2", 0), ("C", "g2", 1), ("g1", "Y1"), ("g2", "Y2")],
    )
    assert expressions_of(c) == {"Y1": "(A AND B)", "Y2": "(A OR C)"}


def test_input_wired_directly_to_output():
    c = circuit(["A"], {}, ["Y"], [("A", "Y")])
    assert expressions_of(c) == {"Y": "A"}


def test_dangling_gate_is_ignored():
    c = circuit(["A", "B"], {"g": "AND", "stray": "NOT"}, ["Y"], [("A", "g", 0), ("B", "g", 1), ("g", "Y")])
    assert expressions_of(c) == {"Y": "(A AND B)"}


def test_rendered_length_matches_render_and_handles_shared_dag():
    a = Variable("A")
    expr = Or((And((a, Variable("B"))), Not(a)))
    assert rendered_length(expr) == len(render_expression(expr))
    # A chain of 60 gates each using the previous node twice has 2^60 leaves when rendered.
    node = a
    for _ in range(60):
        node = And((node, node))
    assert rendered_length(node) > 10**18


def test_evaluate_uses_memo_for_shared_nodes():
    node = Variable("A")
    for _ in range(200):
        node = Or((node, node))
    assert evaluate(node, {"A": True}) is True
    assert evaluate(node, {"A": False}) is False


def test_evaluate_missing_variable():
    with pytest.raises(MissingVariableError):
        evaluate(Variable("Z"), {"A": True})


# ---- parser -------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "source, rendered",
    [
        ("A AND B", "(A AND B)"),
        ("a and b", "(a AND b)"),
        ("A & B | C", "((A AND B) OR C)"),
        ("A | B & C", "(A OR (B AND C))"),
        ("A AND B AND C", "(A AND B AND C)"),
        ("NOT A AND B", "((NOT A) AND B)"),
        ("!(A + B)", "(NOT (A OR B))"),
        ("A' * B", "((NOT A) AND B)"),
        ("A ^ B | C", "((A XOR B) OR C)"),
        ("A NAND B NAND C", "((A NAND B) NAND C)"),
        ("A AND B NAND C", "((A AND B) NAND C)"),
        ("A NAND B AND C", "((A NAND B) AND C)"),
        ("~~A", "(NOT (NOT A))"),
        ("A OR 1", "(A OR 1)"),
        ("Cin XNOR B_2", "(Cin XNOR B_2)"),
        ("A'B + A B'", "(((NOT A) AND B) OR (A AND (NOT B)))"),
        ("A(B + C)", "(A AND (B OR C))"),
        ("(A + B)(C + D)", "((A OR B) AND (C OR D))"),
        ("A !B", "(A AND (NOT B))"),
        # Textbook juxtaposition: runs of capital letters are products of single-letter variables.
        ("AB + C", "((A AND B) OR C)"),
        ("A'BC + ACB'", "(((NOT A) AND B AND C) OR (A AND C AND (NOT B)))"),
        ("ABC'", "(A AND B AND (NOT C))"),
        ("(AB)'", "(NOT (A AND B))"),
        ("A'B'", "((NOT A) AND (NOT B))"),
        # Names with lowercase letters, digits or underscores stay whole.
        ("Cin Cout", "(Cin AND Cout)"),
        ("S1 + A_B", "(S1 OR A_B)"),
        ("ab", "ab"),
        # Operator words are still operators, in any case.
        ("A NOR B", "(A NOR B)"),
        ("a nand b", "(a NAND b)"),
    ],
)
def test_parse_expression(source, rendered):
    assert render_expression(parse_expression(source)) == rendered


def test_known_variables_are_not_split():
    assert render_expression(parse_expression("CIN + AB", known_variables=["CIN", "A", "B"])) == "(CIN OR (A AND B))"
    assert render_expression(parse_expression("CIN + AB")) == "((C AND I AND N) OR (A AND B))"


@pytest.mark.parametrize("source", ["", "A AND", "(A OR B", "A B )", "A $ B", "AND", "A OR )", "10"])
def test_parse_errors(source):
    with pytest.raises(ExpressionParseError):
        parse_expression(source)
