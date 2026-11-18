"""The checker must never crash, whatever a student (or an AI) wires.

Every stored circuit is mutated at random (wires and gates deleted, gate types and pin numbers changed,
loops and duplicates added) and analysed against its exercise. Any answer is fine, including errors;
an exception would be a 500 for the student, so none may escape.
"""

import copy
import random

import pytest
from pydantic import ValidationError

from app.ai.client import MockAIValidator
from app.analysis.gates import GATE_DEFINITIONS
from app.config import Settings
from app.generator.layout import apply_layout
from app.models.circuit import Circuit
from app.services.golden_repository import GoldenRepository
from app.services.task_repository import TaskRepository
from app.services.validation_service import ValidationService

MUTATIONS_PER_TASK = 250
GATE_TYPES = list(GATE_DEFINITIONS)


def mutate(circuit: dict, rng: random.Random) -> dict:
    c = copy.deepcopy(circuit)
    for _ in range(rng.randint(1, 4)):
        gates, conns = c["gates"], c["connections"]
        kind = rng.choice(["drop_wire", "drop_gate", "retype", "resize", "pin", "out_pin", "loop", "duplicate", "relabel", "swap_source"])
        if kind == "drop_wire" and conns:
            conns.pop(rng.randrange(len(conns)))
        elif kind == "drop_gate" and gates:
            gone = gates.pop(rng.randrange(len(gates)))["id"]
            c["connections"] = [w for w in conns if gone not in (w["from"], w["to"])]
        elif kind == "retype" and gates:
            rng.choice(gates)["type"] = rng.choice(GATE_TYPES)
        elif kind == "resize" and gates:
            rng.choice(gates)["inputs"] = rng.randint(0, 12)
        elif kind == "pin" and conns:
            rng.choice(conns)["input_index"] = rng.choice([None, 0, 1, 2, 7, 99])
        elif kind == "out_pin" and conns:
            rng.choice(conns)["output_index"] = rng.choice([None, 0, 1, 3, 99])
        elif kind == "loop" and gates:
            g = rng.choice(gates)["id"]
            conns.append({"from": g, "to": g, "input_index": rng.choice([0, 1])})
        elif kind == "duplicate" and conns:
            conns.append(dict(rng.choice(conns)))
        elif kind == "relabel" and c["outputs"]:
            rng.choice(c["outputs"])["label"] = rng.choice(["Q", "Y", "S", "X1", "AND"])
        elif kind == "swap_source" and conns and gates:
            rng.choice(conns)["from"] = rng.choice(gates)["id"]
    return c


@pytest.fixture(scope="module")
def service() -> ValidationService:
    return ValidationService(MockAIValidator(), Settings(ai_provider="mock"))


@pytest.mark.parametrize("task", TaskRepository().list(), ids=lambda t: t.id)
def test_mutated_circuits_never_crash_the_checker(service, task):
    rng = random.Random(f"robustness-{task.id}")
    base = GoldenRepository().get(task.id)["circuit"]
    analysed = 0
    for _ in range(MUTATIONS_PER_TASK):
        mutated = mutate(base, rng)
        try:
            circuit = Circuit.model_validate(mutated)
        except ValidationError:
            continue  # the API would answer 422 before the checker runs
        det = service.analyze(task, circuit)
        assert det.structurally_valid in (True, False)
        analysed += 1
    assert analysed > MUTATIONS_PER_TASK // 2, "most mutations should still be valid input"


def test_layout_copes_with_whatever_the_ai_returns(service):
    """Layout runs on circuits that passed the check, but must not fail on odd ones either."""
    rng = random.Random("layout")
    for task in TaskRepository().list():
        base = GoldenRepository().get(task.id)["circuit"]
        for _ in range(10):
            try:
                mutated = mutate(base, rng)
                Circuit.model_validate(mutated)
            except ValidationError:
                continue
            try:
                apply_layout(mutated)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"{task.id}: layout raised {type(exc).__name__}: {exc}")
