import random
from itertools import product

import pytest

from app.analysis.boolean_ast import render_expression
from app.analysis.evaluator import evaluate
from app.analysis.minimize import minimize_sop


def column(expr, variables):
    return [evaluate(expr, dict(zip(variables, bits))) for bits in product((False, True), repeat=len(variables))]


@pytest.mark.parametrize(
    "variables, ones, dont_cares, expected",
    [
        (["A", "B"], {3}, set(), "(A AND B)"),
        (["A", "B"], {1, 2, 3}, set(), "(B OR A)"),
        (["A", "B"], {1, 2}, set(), "(((NOT A) AND B) OR (A AND (NOT B)))"),
        (["A"], {0}, set(), "(NOT A)"),
        (["A", "B"], set(), set(), "0"),
        (["A", "B"], {0, 1, 2, 3}, set(), "1"),
        (["A", "B"], {3}, {0, 1, 2}, "1"),  # don't-cares can make it constant
        # Majority of three
        (["A", "B", "C"], {3, 5, 6, 7}, set(), "((B AND C) OR (A AND C) OR (A AND B))"),
        # 2:1 mux (S, A, B): Y = A when S=0, B when S=1
        (["S", "A", "B"], {2, 3, 5, 7}, set(), "(((NOT S) AND A) OR (S AND B))"),
    ],
)
def test_known_minimizations(variables, ones, dont_cares, expected):
    assert render_expression(minimize_sop(variables, ones, dont_cares)) == expected


def test_dont_cares_simplify():
    # Y = 1 when B = 1; row A=1,B=0 is free. Using it would not help, so the result is just B.
    assert render_expression(minimize_sop(["A", "B"], {1, 3}, {2})) == "B"


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_every_function_matches_its_table(n):
    variables = [f"V{i}" for i in range(n)]
    rows = 1 << n
    rng = random.Random(n)
    functions = range(1 << rows) if n <= 3 else [rng.getrandbits(rows) for _ in range(300)]
    for f in functions:
        ones = {r for r in range(rows) if f >> r & 1}
        # Randomly turn some zero rows into don't-cares.
        dont_cares = {r for r in range(rows) if r not in ones and rng.random() < 0.3}
        expr = minimize_sop(variables, ones, dont_cares)
        col = column(expr, variables)
        for r in range(rows):
            if r in dont_cares:
                continue
            assert col[r] == (r in ones), (f, r, render_expression(expr))
