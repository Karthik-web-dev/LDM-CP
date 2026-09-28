import pytest

from app.analysis.equivalence import are_equivalent, compare_columns, map_outputs
from app.analysis.expression_parser import parse_expression as p
from app.analysis.truth_table import generate_truth_table


@pytest.mark.parametrize(
    "a, b",
    [
        ("A AND B", "B AND A"),
        ("A OR (B AND C)", "(A OR B) AND (A OR C)"),
        ("NOT (A AND B)", "NOT A OR NOT B"),  # De Morgan
        ("NOT (A OR B)", "A NOR B"),
        ("A XOR B", "(A AND NOT B) OR (NOT A AND B)"),
        ("A AND B", "NOT (A NAND B)"),
        ("A", "(A AND B) OR (A AND NOT B)"),  # different variable sets, same function
        ("A OR NOT A", "1"),
        ("NOT (NOT A)", "A"),
    ],
)
def test_equivalent(a, b):
    assert are_equivalent(p(a), p(b))


@pytest.mark.parametrize(
    "a, b",
    [
        ("A AND B", "A OR B"),
        ("A AND B", "A AND C"),
        ("A XOR B", "A XNOR B"),
        ("(A AND B) OR C", "A AND (B OR C)"),
    ],
)
def test_not_equivalent(a, b):
    assert not are_equivalent(p(a), p(b))


def test_compare_columns_reports_counterexamples():
    vars_ = ["A", "B"]
    actual = generate_truth_table({"Y": p("A OR B")}, vars_, 12)
    expected = generate_truth_table({"Y": p("A AND B")}, vars_, 12)
    result = compare_columns(actual, "Y", expected, "Y")
    assert not result.equivalent
    assert result.mismatch_count == 2
    assert [(c.inputs, c.expected, c.actual) for c in result.counterexamples] == [
        ({"A": 0, "B": 1}, 0, 1), ({"A": 1, "B": 0}, 0, 1),
    ]


def test_compare_columns_requires_same_variables():
    with pytest.raises(ValueError):
        compare_columns(
            generate_truth_table({"Y": p("A")}, ["A", "B"], 12), "Y",
            generate_truth_table({"Y": p("A")}, ["B", "A"], 12), "Y",
        )


def test_map_outputs_single_output_ignores_label():
    mapping, extra = map_outputs(["Y"], ["OUT"])
    assert (mapping[0].expected_output, mapping[0].circuit_output, mapping[0].label_mismatch) == ("Y", "OUT", True)
    assert extra == []


def test_map_outputs_multi_by_label():
    mapping, extra = map_outputs(["S", "C"], ["C", "X"])
    assert [(m.expected_output, m.circuit_output) for m in mapping] == [("S", None), ("C", "C")]
    assert extra == ["X"]
