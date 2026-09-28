"""User-defined targets: equations and truth tables (with don't-cares)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai.client import MockAIValidator
from app.api.dependencies import get_validation_service
from app.config import Settings
from app.main import app
from app.models.task import Task
from app.services.validation_service import ValidationService
from tests.helpers import make_circuit


@pytest.fixture
def ai():
    return MockAIValidator()


@pytest.fixture
def client(ai):
    service = ValidationService(ai, Settings(ai_provider="mock"))
    app.dependency_overrides[get_validation_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def table_task(column, inputs=("A", "B"), label="Y"):
    return {"id": "custom", "inputs": list(inputs), "outputs": [label], "expected_truth_table": {label: column}}


def gate_circuit(gate):
    return make_circuit(["A", "B"], {"g1": gate}, ["Y"], [("A", "g1", 0), ("B", "g1", 1), ("g1", "Y")])


def validate(client, circuit, task):
    r = client.post("/api/v1/validate", json={"task": task, "circuit": circuit})
    assert r.status_code == 200, r.text
    return r.json()


# ---- truth-table targets ------------------------------------------------------------------

def test_truth_table_target_correct(client):
    body = validate(client, gate_circuit("XOR"), table_task([0, 1, 1, 0]))
    assert body["is_correct"]
    [cmp] = body["deterministic"]["comparisons"]
    assert cmp["expected_defined_by"] == "truth_table"
    assert cmp["expected_expression"] == "(((NOT A) AND B) OR (A AND (NOT B)))"


def test_truth_table_target_incorrect_has_counterexamples(client):
    body = validate(client, gate_circuit("OR"), table_task([0, 1, 1, 0]))
    assert not body["is_correct"]
    [cmp] = body["deterministic"]["comparisons"]
    assert cmp["mismatch_count"] == 1
    assert cmp["counterexamples"] == [{"inputs": {"A": 1, "B": 1}, "expected": 0, "actual": 1}]


def test_dont_care_rows_accept_either_value(client):
    column = [0, 1, 1, "X"]  # last row free: both OR and XOR satisfy it
    assert validate(client, gate_circuit("OR"), table_task(column))["is_correct"]
    assert validate(client, gate_circuit("XOR"), table_task(column))["is_correct"]
    assert not validate(client, gate_circuit("AND"), table_task(column))["is_correct"]
    body = validate(client, gate_circuit("OR"), table_task(column))
    assert body["deterministic"]["expected_truth_table"]["rows"][3]["outputs"] == [None]


def test_truth_table_target_ignores_extra_circuit_input_only_if_unused(client):
    # Circuit has an extra input C that it does not use: still equivalent.
    c = make_circuit(["A", "B", "C"], {"g1": "AND"}, ["Y"], [("A", "g1", 0), ("B", "g1", 1), ("g1", "Y")])
    body = validate(client, c, table_task([0, 0, 0, 1]))
    assert body["is_correct"]
    assert "EXTRA_INPUT" in [w["type"] for w in body["deterministic"]["warnings"]]


def test_multi_output_truth_table(client):
    task = {"id": "custom", "inputs": ["A", "B"], "outputs": ["S", "C"],
            "expected_truth_table": {"S": [0, 1, 1, 0], "C": [0, 0, 0, 1]}}
    c = make_circuit(["A", "B"], {"x": "XOR", "a": "AND"}, ["S", "C"], [
        ("A", "x", 0), ("B", "x", 1), ("A", "a", 0), ("B", "a", 1), ("x", "S"), ("a", "C"),
    ])
    assert validate(client, c, task)["is_correct"]


def test_ai_payload_marks_dont_cares(client, ai):
    validate(client, gate_circuit("OR"), table_task([0, 1, 1, "X"]))
    payload = ai.calls[0]
    target = payload["task"]["expected_outputs"]["Y"]
    assert target["defined_by"] == "truth_table" and target["column"] == [0, 1, 1, "X"]
    assert payload["deterministic_analysis"]["truth_table"][3]["expected"] == {"Y": "X"}


@pytest.mark.parametrize("cells, normalized", [(["x", "-", None, "1"], ["X", "X", "X", 1]), (["0", 1, "X", 0], [0, 1, "X", 0])])
def test_cell_normalization(cells, normalized):
    assert Task.model_validate(table_task(cells)).expected_truth_table == {"Y": normalized}


@pytest.mark.parametrize(
    "task",
    [
        table_task([0, 1, 1]),  # wrong length
        {"id": "c", "inputs": [], "expected_truth_table": {"Y": [0]}},  # no inputs
        table_task([0, 1, 1, 2]),  # invalid value
        table_task([0, 1, 1, 0], inputs=("A", "A")),  # duplicate inputs
        table_task([0, 1, 1, 0], inputs=("A", "and")),  # operator name
        table_task([0, 1, 1, 0], label="my output"),  # bad output name
        {"id": "c", "inputs": ["A"], "expected_expression": "A", "expected_truth_table": {"Y": [0, 1]}},  # two definitions
        {"id": "c", "inputs": ["A"]},  # no definition
    ],
)
def test_invalid_truth_table_tasks(task):
    with pytest.raises(ValidationError):
        Task.model_validate(task)


def test_invalid_task_returns_422(client):
    r = client.post("/api/v1/validate", json={"task": table_task([0, 1]), "circuit": gate_circuit("AND")})
    assert r.status_code == 422


# ---- equation targets typed by the user ---------------------------------------------------

def test_custom_equation_target_textbook_notation(client):
    for expr in ("A'B + AB'", "A'B + A B'", "A' B + A B'"):
        task = {"id": "custom", "expected_expression": expr}
        body = validate(client, gate_circuit("XOR"), task)
        assert body["is_correct"], expr
        assert body["deterministic"]["variables"] == ["A", "B"]


def test_preview_splits_letter_runs(client):
    body = client.post("/api/v1/tasks/preview", json={"id": "custom", "expected_expression": "A'BC + ACB'"}).json()
    assert body["valid"] and body["inputs"] == ["A", "B", "C"]
    assert body["expressions"] == {"Y": "(((NOT A) AND B AND C) OR (A AND C AND (NOT B)))"}
    # A'BC + AB'C = C AND (A XOR B)
    assert [r["outputs"][0] for r in body["truth_table"]["rows"]] == [0, 0, 0, 1, 0, 1, 0, 0]


def test_custom_equation_target_with_unparseable_text(client):
    body = validate(client, gate_circuit("XOR"), {"id": "custom", "expected_expression": "A +* B"})
    assert body["deterministic"]["errors"][0]["type"] == "INVALID_TASK"


# ---- preview ------------------------------------------------------------------------------

def test_preview_equation(client):
    r = client.post("/api/v1/tasks/preview", json={"id": "custom", "expected_expression": "(A AND B) OR C"})
    body = r.json()
    assert body["valid"] and body["inputs"] == ["A", "B", "C"]
    assert body["expressions"] == {"Y": "((A AND B) OR C)"}
    assert body["simplified"] == {"Y": "(C OR (A AND B))"}
    assert [row["outputs"][0] for row in body["truth_table"]["rows"]] == [0, 1, 0, 1, 0, 1, 1, 1]


def test_preview_truth_table(client):
    r = client.post("/api/v1/tasks/preview", json=table_task([1, 1, 0, "X"]))
    body = r.json()
    assert body["valid"]
    assert body["expressions"] == {"Y": "(NOT A)"}
    assert body["truth_table"]["rows"][3]["outputs"] == [None]


def test_preview_reports_parse_errors(client):
    body = client.post("/api/v1/tasks/preview", json={"id": "custom", "expected_expression": "A AND (B"}).json()
    assert body["valid"] is False and "could not be parsed" in body["errors"][0]


def test_preview_input_order_follows_task(client):
    body = client.post("/api/v1/tasks/preview", json={"id": "c", "expected_expression": "B AND A", "inputs": ["B", "A"]}).json()
    assert body["inputs"] == ["B", "A"]
