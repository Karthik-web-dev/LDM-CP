import pytest

from app.analysis.boolean_ast import And, Nand, Nor, Not, Or, Variable, Xnor, Xor
from app.analysis.expression_parser import parse_expression
from app.analysis.truth_table import TooManyVariablesError, assignments, generate_truth_table

A, B = Variable("A"), Variable("B")


def column(expr, variables=("A", "B")):
    table = generate_truth_table({"Y": expr}, list(variables), 12)
    return [row.outputs[0] for row in table.rows]


def test_row_order_is_binary_counting():
    assert [tuple(int(v) for v in env.values()) for env in assignments(["A", "B"])] == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_and_truth_table_matches_spec():
    table = generate_truth_table({"Y": And((A, B))}, ["A", "B"], 12)
    assert table.variables == ["A", "B"] and table.outputs == ["Y"]
    assert [(r.inputs, r.outputs) for r in table.rows] == [
        ([0, 0], [0]), ([0, 1], [0]), ([1, 0], [0]), ([1, 1], [1]),
    ]


@pytest.mark.parametrize(
    "expr, expected",
    [
        (And((A, B)), [0, 0, 0, 1]),
        (Or((A, B)), [0, 1, 1, 1]),
        (Nand((A, B)), [1, 1, 1, 0]),
        (Nor((A, B)), [1, 0, 0, 0]),
        (Xor((A, B)), [0, 1, 1, 0]),
        (Xnor((A, B)), [1, 0, 0, 1]),
    ],
)
def test_gate_semantics(expr, expected):
    assert column(expr) == expected


def test_not():
    assert column(Not(A), ["A"]) == [1, 0]


def test_three_input_xor_is_parity():
    expr = Xor((A, B, Variable("C")))
    assert column(expr, ["A", "B", "C"]) == [0, 1, 1, 0, 1, 0, 0, 1]


def test_three_input_xnor_is_even_parity():
    expr = Xnor((A, B, Variable("C")))
    assert column(expr, ["A", "B", "C"]) == [1, 0, 0, 1, 0, 1, 1, 0]


def test_extra_variables_are_ignored_by_expression():
    assert column(A, ["A", "B"]) == [0, 0, 1, 1]


def test_multiple_outputs():
    table = generate_truth_table({"S": parse_expression("A XOR B"), "C": parse_expression("A AND B")}, ["A", "B"], 12)
    assert table.outputs == ["S", "C"]
    assert [r.outputs for r in table.rows] == [[0, 0], [1, 0], [1, 0], [0, 1]]


def test_zero_variables():
    table = generate_truth_table({"Y": parse_expression("1")}, [], 12)
    assert [(r.inputs, r.outputs) for r in table.rows] == [([], [1])]


def test_variable_limit():
    with pytest.raises(TooManyVariablesError):
        generate_truth_table({"Y": A}, [f"V{i}" for i in range(13)], 12)
