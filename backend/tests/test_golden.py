"""The demo safety net: every built-in exercise has a stored circuit and that circuit passes it."""

import pytest
from fastapi.testclient import TestClient

from app.analysis.structural_validator import validate_structure
from app.config import Limits
from app.generator.circuit_builder import circuit_from_expressions
from app.generator.layout import apply_layout
from app.analysis.expression_parser import parse_expression
from app.main import app
from app.models.circuit import Circuit
from app.services.golden_repository import GoldenRepository
from app.services.task_repository import TaskRepository
from app.tools.backtest import run_backtest


def test_every_exercise_has_a_passing_golden_circuit():
    rows = run_backtest()
    assert rows, "no exercises found"
    failures = [f"{r.task_id}: {r.detail}" for r in rows if not r.ok]
    assert not failures, failures


def test_golden_files_have_no_orphans():
    tasks = {t.id for t in TaskRepository().list()}
    assert set(GoldenRepository().ids()) <= tasks


def test_every_user_assignment_is_covered():
    """The seven lab assignments map to these exercises; deleting one must fail loudly."""
    required = {
        "gates_verification", "boolean_simplification",  # 1. gates and Boolean algebra
        "excess3_to_bcd", "bcd_to_excess3",  # 2. K-map code converters
        "full_adder_mux_74153",  # 3. multiplexer
        "comparator_2bit_74138",  # 4. decoder
        "async_up_counter_2bit", "async_down_counter_2bit",  # 5. asynchronous counter
        "sync_updown_counter_2bit",  # 6. synchronous counter
        "shift_register_4bit",  # 7. shift register
        "sr_latch_nand", "sr_flipflop_nand",  # NAND-gate latches (feedback)
    }
    assert required <= set(GoldenRepository().ids())


def test_golden_circuits_are_placed_without_overlap():
    for task_id in GoldenRepository().ids():
        circuit = GoldenRepository().get(task_id)["circuit"]
        boxes = []
        for key in ("inputs", "gates", "outputs"):
            for item in circuit[key]:
                assert "position" in item, (task_id, item["id"])
                boxes.append((item["id"], item["position"]["x"], item["position"]["y"]))
        # two components must never sit at the same spot
        assert len({(x, y) for _, x, y in boxes}) == len(boxes), task_id


def test_golden_endpoints():
    client = TestClient(app)
    assert "full_adder_mux_74153" in GoldenRepository().ids()
    body = client.get("/api/v1/golden/full_adder_mux_74153").json()
    assert body["task_id"] == "full_adder_mux_74153"
    Circuit.model_validate(body["circuit"])
    assert client.get("/api/v1/golden/does_not_exist").status_code == 404
    assert client.get("/api/v1/golden/..%2Fsecrets").status_code in (404, 422)


@pytest.mark.parametrize("source", ["A AND B", "(A AND NOT B) OR C"])
def test_expression_builder_and_layout_produce_a_valid_circuit(source):
    expr = parse_expression(source, known_variables=["A", "B", "C"])
    circuit = apply_layout(circuit_from_expressions(["A", "B", "C"], {"Y": expr}))
    report = validate_structure(Circuit.model_validate(circuit), Limits())
    assert not report.errors
