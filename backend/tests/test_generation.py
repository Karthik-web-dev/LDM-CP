"""AI circuit generation: verification, retries with the exact errors, stored-circuit fallback, demo mode."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.ai.client import MockAIValidator
from app.ai.validator import AIValidationError
from app.config import Settings
from app.main import app
from app.models.task import Task
from app.services.generation_service import GenerationService, extract_circuit
from app.services.golden_repository import GoldenRepository
from app.services.task_repository import TaskRepository
from app.services.validation_service import ValidationService


def golden_json(task_id: str) -> dict:
    circuit = GoldenRepository().get(task_id)["circuit"]
    return {
        "version": 1,
        **{k: [{x: v for x, v in item.items() if x != "position"} for item in circuit[k]] for k in ("inputs", "gates", "outputs")},
        "connections": [{k: v for k, v in c.items() if v is not None} for c in circuit["connections"]],
    }


def reply(circuit: dict, fenced: bool = False) -> str:
    text = json.dumps({"circuit": circuit, "explanation": "ok"})
    return f"Here you go:\n```json\n{text}\n```" if fenced else text


def broken_half_adder() -> dict:
    circuit = golden_json("half_adder")
    for gate in circuit["gates"]:
        gate["type"] = "OR" if gate["type"] == "AND" else gate["type"]  # carry becomes A OR B
    return circuit


def make(ai: MockAIValidator, golden: GoldenRepository | None = None, **settings) -> GenerationService:
    cfg = Settings(ai_provider="mock", **settings)
    return GenerationService(ai, ValidationService(ai, cfg), golden or GoldenRepository(), cfg)


def task(task_id: str = "half_adder") -> Task:
    found = TaskRepository().get(task_id)
    assert found is not None
    return found


def run(coro):
    return asyncio.run(coro)


def test_a_correct_first_answer_is_verified_and_laid_out():
    ai = MockAIValidator(generations=[reply(golden_json("half_adder"), fenced=True)])
    result = run(make(ai).generate(task()))
    assert result.success and result.source == "ai" and result.attempts == 1
    assert all("position" in c for c in result.circuit["gates"])  # placed for the editor


def test_unknown_fields_in_the_reply_are_ignored():
    data = golden_json("half_adder")
    data["gates"][0]["colour"] = "red"
    data["connections"][0]["note"] = "x"
    cleaned, _ = extract_circuit(reply(data))
    assert "colour" not in cleaned["gates"][0] and "note" not in cleaned["connections"][0]


def test_a_wrong_answer_is_retried_with_the_exact_problems():
    ai = MockAIValidator(generations=[reply(broken_half_adder()), reply(golden_json("half_adder"))])
    result = run(make(ai).generate(task()))
    assert result.source == "ai" and result.attempts == 2
    second_user_prompt = ai.generation_prompts[1][1]
    assert "Your previous attempt failed" in second_user_prompt
    assert "expected" in second_user_prompt  # the counterexample row is quoted back


def test_never_correct_falls_back_to_the_stored_circuit():
    ai = MockAIValidator(generations=[reply(broken_half_adder())] * 3)
    result = run(make(ai).generate(task()))
    assert result.success and result.source == "fallback" and result.attempts == 3
    assert "stored circuit" in (result.notice or "")


@pytest.mark.parametrize("error", [AIValidationError("timeout", "The AI took too long to respond."), RuntimeError("boom")])
def test_ai_errors_fall_back_instead_of_failing(error):
    result = run(make(MockAIValidator(error=error)).generate(task()))
    assert result.success and result.source == "fallback"


def test_garbage_replies_fall_back():
    ai = MockAIValidator(generations=["I cannot do that.", "{not json", '{"circuit": 5}'])
    result = run(make(ai).generate(task()))
    assert result.source == "fallback"


def test_a_slow_ai_times_out_into_the_fallback():
    class Slow(MockAIValidator):
        async def complete_json(self, system, user):
            await asyncio.sleep(5)
            return "{}"

    result = run(make(Slow(), generate_timeout_seconds=0.05).generate(task()))
    assert result.source == "fallback"


def test_demo_mode_never_calls_the_ai():
    ai = MockAIValidator(error=RuntimeError("the AI must not be called in demo mode"))
    result = run(make(ai).generate(task(), mode="demo"))
    assert result.success and result.source == "stored" and ai.generation_prompts == []


def test_without_a_stored_circuit_a_failure_is_reported_not_faked(tmp_path):
    result = run(make(MockAIValidator(error=RuntimeError("x")), GoldenRepository(tmp_path)).generate(task()))
    assert not result.success and result.source == "none" and result.circuit is None


def test_the_prompt_names_every_part_and_the_exact_labels():
    ai = MockAIValidator(generations=[reply(golden_json("half_adder"))])
    run(make(ai).generate(task()))
    system, user = ai.generation_prompts[0]
    for part in ("7476", "7474", "74138", "74153", "VCC", "MUX4", "DECODER3"):
        assert part in system
    assert "Output labels: S, C" in user


def test_generate_endpoint_demo_mode_and_errors():
    client = TestClient(app)
    ok = client.post("/api/v1/generate", json={"task_id": "excess3_to_bcd", "mode": "demo"}).json()
    assert ok["success"] and ok["source"] == "stored" and ok["circuit"]["gates"]
    assert client.post("/api/v1/generate", json={"task_id": "nope", "mode": "demo"}).status_code == 404
    assert client.post("/api/v1/generate", json={"mode": "demo"}).status_code == 422
