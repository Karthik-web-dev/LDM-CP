import pytest
from fastapi.testclient import TestClient

from app.ai.client import MockAIValidator
from app.analysis.expected_function import build_expected, expected_truth_table
from app.analysis.kmap import KMapError, build_kmap, gray_code
from app.api.dependencies import get_validation_service
from app.config import Settings
from app.main import app
from app.models.task import Task
from app.services.validation_service import ValidationService
from tests.helpers import make_circuit


def kmap_of(expr=None, table=None, inputs=()):
    task = Task.model_validate(
        {"id": "t", "inputs": list(inputs), "expected_truth_table": {"Y": table}} if table
        else {"id": "t", "expected_expression": expr, "inputs": list(inputs)}
    )
    outputs, _ = build_expected(task)
    variables = list(inputs) or sorted(set().union(*(o.variables for o in outputs)))
    return build_kmap(expected_truth_table(outputs, variables, 12), "Y")


def grid(k):
    return [["X" if c.value is None else c.value for c in row] for row in k.cells]


def test_gray_code():
    assert gray_code(1) == [0, 1]
    assert gray_code(2) == [0, 1, 3, 2]


def test_two_variable_layout():
    k = kmap_of("A AND B")
    assert (k.row_variables, k.col_variables) == (["A"], ["B"])
    assert (k.row_labels, k.col_labels) == (["0", "1"], ["0", "1"])
    assert grid(k) == [[0, 0], [0, 1]]
    assert [g.term for g in k.groups] == ["AB"] and k.minimal_sop == "AB"


def test_three_variable_gray_columns_and_minterm_positions():
    k = kmap_of("A'BC + AB'C")
    assert (k.row_variables, k.col_variables) == (["A"], ["B", "C"])
    assert k.col_labels == ["00", "01", "11", "10"]
    # minterm at row r, col c = (A << 2) | BC in Gray order
    assert [[c.minterm for c in row] for row in k.cells] == [[0, 1, 3, 2], [4, 5, 7, 6]]
    assert grid(k) == [[0, 0, 1, 0], [0, 1, 0, 0]]
    assert sorted(g.term for g in k.groups) == ["A'BC", "AB'C"]


def test_four_variable_wraparound_corners():
    # Four corners of a 4-variable map: B'D'
    k = kmap_of("B' D'", inputs=["A", "B", "C", "D"])
    assert (k.row_variables, k.col_variables) == (["A", "B"], ["C", "D"])
    [g] = k.groups
    assert g.term == "B'D'"
    assert sorted(map(tuple, g.cells)) == [(0, 0), (0, 3), (3, 0), (3, 3)]


def test_dont_cares_are_shown_and_used():
    # Rows (A,B,C): ones at 1,3,5 ; X at 7 -> C  (using the don't-care)
    k = kmap_of(table=[0, 1, 0, 1, 0, 1, 0, "X"], inputs=["A", "B", "C"])
    assert k.dont_cares == [7] and k.minterms == [1, 3, 5]
    assert k.minimal_sop == "C"
    assert grid(k) == [[0, 1, 1, 0], [0, 1, "X", 0]]


def test_constant_functions():
    assert kmap_of("A AND NOT A").minimal_sop == "0"
    k = kmap_of("A OR NOT A")
    assert k.minimal_sop == "1" and len(k.groups[0].cells) == 2


def test_multi_letter_names_use_dot():
    k = kmap_of("A AND Cin", inputs=["A", "Cin"])
    assert k.minimal_sop == "A·Cin"


def test_too_many_variables():
    with pytest.raises(KMapError):
        kmap_of("A B C D E")


# ---- API -----------------------------------------------------------------------------------

@pytest.fixture
def client():
    ai = MockAIValidator()
    service = ValidationService(ai, Settings(ai_provider="mock"))
    app.dependency_overrides[get_validation_service] = lambda: service
    yield TestClient(app), ai
    app.dependency_overrides.clear()


def test_kmap_endpoint_target_and_circuit(client):
    c, _ = client
    r = c.post("/api/v1/kmap", json={"task_id": "half_adder", "source": "target"}).json()
    assert r["errors"] == [] and [k["output"] for k in r["kmaps"]] == ["S", "C"]
    assert r["kmaps"][1]["minimal_sop"] == "AB"

    circuit = make_circuit(["A", "B"], {"g": "OR"}, ["Y"], [("A", "g", 0), ("B", "g", 1), ("g", "Y")])
    r = c.post("/api/v1/kmap", json={"task_id": "and_gate_001", "source": "circuit", "circuit": circuit}).json()
    assert r["source"] == "circuit" and r["kmaps"][0]["minimal_sop"] in ("A + B", "B + A")


def test_kmap_endpoint_errors(client):
    c, _ = client
    broken = make_circuit(["A", "B"], {"g": "AND"}, ["Y"], [("A", "g", 0), ("g", "Y")])
    r = c.post("/api/v1/kmap", json={"task_id": "and_gate_001", "source": "circuit", "circuit": broken}).json()
    assert r["kmaps"] == [] and "Complete the circuit first" in r["errors"][0]
    assert c.post("/api/v1/kmap", json={"task_id": "and_gate_001", "source": "circuit"}).status_code == 422
    r = c.post("/api/v1/kmap", json={"task": {"id": "x", "expected_expression": "A B C D E"}}).json()
    assert "1 to 4 inputs" in r["errors"][0]


# ---- hint mode -----------------------------------------------------------------------------

def test_hint_mode_runs_on_incomplete_circuit(client):
    c, ai = client
    empty = make_circuit(["A", "B"], {}, ["Y"], [])
    body = c.post("/api/v1/validate", json={"task_id": "and_gate_001", "circuit": empty, "ai_mode": "hint"}).json()
    assert not body["is_correct"]
    assert body["ai"]["available"] and body["ai"]["summary"].startswith("(Mock tutor) Hint")
    assert ai.modes == ["hint"]
    assert ai.calls[0]["deterministic_analysis"]["errors"][0]["type"] == "UNDRIVEN_OUTPUT"


def test_feedback_mode_still_skips_incomplete_circuit(client):
    c, ai = client
    empty = make_circuit(["A", "B"], {}, ["Y"], [])
    body = c.post("/api/v1/validate", json={"task_id": "and_gate_001", "circuit": empty}).json()
    assert body["ai"]["available"] is False and "ask for a hint" in body["ai"]["skipped_reason"]
    assert ai.calls == []


def test_hint_prompt_is_outside_the_data_block():
    from app.ai.prompts import build_user_message
    msg = build_user_message({"x": 1}, "hint")
    assert msg.index("HINT") < msg.index("<analysis_data>")
