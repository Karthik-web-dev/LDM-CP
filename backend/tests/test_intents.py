"""AI build modes beyond "target": describe-only requests and improving an existing circuit."""

import asyncio
import json

from fastapi.testclient import TestClient

from app.ai.client import MockAIValidator
from app.config import Settings
from app.generator.layout import apply_layout
from app.main import app
from app.models.circuit import Circuit
from app.services.demo_matcher import DemoMatcher
from app.services.generation_service import GenerationService
from app.services.golden_repository import GoldenRepository
from app.services.task_repository import TaskRepository
from app.services.validation_service import ValidationService


def golden(task_id: str) -> dict:
    return GoldenRepository().get(task_id)["circuit"]


def bare(circuit: dict) -> dict:
    """The circuit as an AI would send it: no positions."""
    return {
        "version": 1,
        **{k: [{x: v for x, v in item.items() if x != "position"} for item in circuit[k]] for k in ("inputs", "gates", "outputs")},
        "connections": [{k: v for k, v in c.items() if v is not None} for c in circuit["connections"]],
    }


def reply(circuit: dict, spec: dict | None = None) -> str:
    body: dict = {"circuit": bare(circuit), "explanation": "ok"}
    if spec is not None:
        body["spec"] = spec
    return json.dumps(body)


HALF_ADDER_SPEC = {"inputs": ["A", "B"], "outputs": ["S", "C"], "expected_outputs": {"S": "A XOR B", "C": "A AND B"}}


def make(ai: MockAIValidator, **settings) -> GenerationService:
    cfg = Settings(ai_provider="mock", **settings)
    repo = GoldenRepository()
    return GenerationService(ai, ValidationService(ai, cfg), repo, cfg, DemoMatcher(TaskRepository(), repo))


def run(coro):
    return asyncio.run(coro)


def broken_half_adder() -> dict:
    circuit = bare(golden("half_adder"))
    for gate in circuit["gates"]:
        gate["type"] = "OR" if gate["type"] == "AND" else gate["type"]
    return circuit


# ---- describe: plain language only ---------------------------------------------------------------


def test_describe_returns_the_circuit_and_the_target_it_was_built_to():
    ai = MockAIValidator(generations=[reply(golden("half_adder"), HALF_ADDER_SPEC)])
    result = run(make(ai).generate(None, "build a half adder using logic gates", intent="describe"))
    assert result.success and result.source == "ai" and result.attempts == 1
    assert result.spec["expected_outputs"] == HALF_ADDER_SPEC["expected_outputs"]
    assert "own reading" in result.notice
    system, user = ai.generation_prompts[0]
    assert '"spec"' in system and "Student request: build a half adder" in user
    assert "Exercise:" not in user  # no target is provided


def test_describe_without_a_spec_is_told_to_add_one():
    ai = MockAIValidator(generations=[reply(golden("half_adder")), reply(golden("half_adder"), HALF_ADDER_SPEC)])
    result = run(make(ai).generate(None, "half adder", intent="describe"))
    assert result.source == "ai" and result.attempts == 2
    assert "needs a \"spec\"" in ai.generation_prompts[1][1]


def test_describe_circuit_must_do_what_its_own_spec_says():
    ai = MockAIValidator(generations=[reply(broken_half_adder(), HALF_ADDER_SPEC), reply(golden("half_adder"), HALF_ADDER_SPEC)])
    result = run(make(ai).generate(None, "half adder", intent="describe"))
    assert result.attempts == 2
    assert "expected" in ai.generation_prompts[1][1]  # the failing row is quoted back


def test_describe_labels_must_match_the_spec():
    spec = {**HALF_ADDER_SPEC, "outputs": ["Sum", "Carry"], "expected_outputs": {"Sum": "A XOR B", "Carry": "A AND B"}}
    ai = MockAIValidator(generations=[reply(golden("half_adder"), spec), reply(golden("half_adder"), HALF_ADDER_SPEC)])
    result = run(make(ai).generate(None, "half adder", intent="describe"))
    assert result.attempts == 2 and "must be identical" in ai.generation_prompts[1][1]


def test_describe_accepts_a_sequence_spec_for_a_counter():
    spec = {
        "inputs": ["CLK"], "outputs": ["Q1", "Q0"],
        "sequence": {"clock": "CLK", "steps": [{"outputs": {"Q1": 0, "Q0": 1}}, {"outputs": {"Q1": 1, "Q0": 0}}]},
    }
    ai = MockAIValidator(generations=[reply(golden("async_up_counter_2bit"), spec)])
    result = run(make(ai).generate(None, "2 bit ripple up counter", intent="describe"))
    assert result.source == "ai" and result.spec["sequence"]["clock"] == "CLK"


def test_describe_failure_falls_back_to_a_stored_circuit_that_matches_the_request():
    ai = MockAIValidator(generations=[reply(broken_half_adder(), HALF_ADDER_SPEC)] * 3)
    result = run(make(ai).generate(None, "half adder", intent="describe"))
    assert result.success and result.source == "fallback" and result.matched_task_id == "half_adder"


def test_describe_failure_without_a_matching_stored_circuit_is_reported():
    result = run(make(MockAIValidator(error=RuntimeError("x"))).generate(None, "quantum teleporter", intent="describe"))
    assert not result.success and result.source == "none" and result.circuit is None


def test_describe_in_demo_mode_uses_stored_circuits_only():
    ai = MockAIValidator(error=RuntimeError("the AI must not be called"))
    hit = run(make(ai).generate(None, "full adder using 74153", mode="demo", intent="describe"))
    assert hit.source == "stored" and hit.matched_task_id == "full_adder_mux_74153"
    miss = run(make(ai).generate(None, "quantum teleporter", mode="demo", intent="describe"))
    assert not miss.success and ai.generation_prompts == []


def test_describe_needs_a_request():
    assert not run(make(MockAIValidator()).generate(None, "  ", intent="describe")).success


# ---- extend: build on the existing circuit --------------------------------------------------------


def half_adder_without_carry() -> Circuit:
    """Sum path only: A, B -> XOR -> S. The carry gate and output are missing."""
    full = apply_layout(bare(golden("half_adder")))
    keep_ids = {"input_1", "input_2", "gate_1", "output_1"}
    return Circuit.model_validate({
        "version": 1,
        "inputs": [i for i in full["inputs"] if i["id"] in keep_ids],
        "gates": [g for g in full["gates"] if g["id"] in keep_ids],
        "outputs": [o for o in full["outputs"] if o["id"] in keep_ids],
        "connections": [c for c in full["connections"] if c["from"] in keep_ids and c["to"] in keep_ids],
    })


def test_extend_keeps_existing_positions_and_places_new_parts_clear_of_them():
    existing = half_adder_without_carry()
    before = {item.id: (item.position.x, item.position.y) for group in (existing.inputs, existing.gates, existing.outputs) for item in group}
    ai = MockAIValidator(generations=[reply(golden("half_adder"))])
    task = TaskRepository().get("half_adder")
    result = run(make(ai).generate(task, "add the carry output", intent="extend", existing=existing))
    assert result.success and result.source == "ai"

    placed = {item["id"]: (item["position"]["x"], item["position"]["y"]) for key in ("inputs", "gates", "outputs") for item in result.circuit[key]}
    for node_id, pos in before.items():
        assert placed[node_id] == pos, node_id  # the student's parts did not move
    right_edge = max(x for x, _ in before.values()) + 64
    for node_id in set(placed) - set(before):
        assert placed[node_id][0] >= right_edge, node_id  # new parts sit to the right of the old ones
    assert len(set(placed.values())) == len(placed)

    user = ai.generation_prompts[0][1]
    assert "Current circuit:" in user and "no output labelled C" in user and "add the carry output" in user


def test_extend_does_nothing_when_the_circuit_is_already_correct():
    ai = MockAIValidator(error=RuntimeError("the AI must not be called"))
    existing = Circuit.model_validate(apply_layout(bare(golden("half_adder"))))
    result = run(make(ai).generate(TaskRepository().get("half_adder"), None, intent="extend", existing=existing))
    assert result.success and result.circuit is None and "already matches" in result.notice
    assert ai.generation_prompts == []


def test_extend_failure_never_replaces_the_students_circuit_with_a_stored_one():
    ai = MockAIValidator(generations=[reply(broken_half_adder())] * 3)
    result = run(make(ai).generate(TaskRepository().get("half_adder"), "fix it", intent="extend", existing=half_adder_without_carry()))
    assert not result.success and result.circuit is None and result.source == "none"
    assert "was not changed" in result.notice


def test_extend_needs_a_circuit_on_the_workspace():
    empty = Circuit.model_validate({"version": 1})
    assert not run(make(MockAIValidator()).generate(TaskRepository().get("half_adder"), "go", intent="extend", existing=empty)).success


# ---- endpoint ---------------------------------------------------------------------------------------


def test_generate_endpoint_validates_each_intent():
    client = TestClient(app)
    post = lambda body: client.post("/api/v1/generate", json=body)  # noqa: E731
    assert post({"intent": "describe", "mode": "live"}).status_code == 422  # no request text
    assert post({"intent": "extend", "task_id": "half_adder"}).status_code == 422  # no circuit
    assert post({"intent": "target"}).status_code == 422  # no target
    assert post({"intent": "target", "task_id": "nope"}).status_code == 404

    hit = post({"intent": "describe", "mode": "demo", "prompt": "half adder"}).json()
    assert hit["source"] == "stored" and hit["matched_task_id"] == "half_adder" and hit["circuit"]["gates"]

    miss = post({"intent": "describe", "mode": "demo", "prompt": "quantum teleporter"}).json()
    assert miss["success"] is False and miss["circuit"] is None


# ---- robustness: nothing the model says may crash the pipeline -------------------------------------------------

WEIRD_REPLIES = [
    "", "[]", "null", "42", "{}", "{not json", "```json" + chr(10) + "```", '{"circuit": []}', '{"circuit": {"inputs": "x"}}',
    '{"circuit": {"gates": [{"id": 1, "type": null}]}}', '{"circuit": {"gates": [{"id": "g", "type": "NOPE", "inputs": -3}]}}',
    '{"spec": 5, "circuit": {}}', '{"spec": {"expected_outputs": {"Y": "A AND ("}}, "circuit": {}}',
    '{"spec": {"sequence": {"steps": []}}, "circuit": {}}', '{"circuit": {"connections": [{"from": "a", "to": "b"}]}}',
    "x" * 20000, '{"circuit": ' * 50,
]


def test_garbage_replies_never_crash_any_mode():
    half = Circuit.model_validate(apply_layout(bare(golden("half_adder"))))
    task = TaskRepository().get("half_adder")
    for reply_text in WEIRD_REPLIES:
        for intent in ("describe", "target", "extend"):
            ai = MockAIValidator(generations=[reply_text] * 3)
            result = run(make(ai).generate(None if intent == "describe" else task, "half adder" if intent == "describe" else "go", intent=intent, existing=half))
            assert result is not None
            assert result.source in ("none", "fallback", "ai"), (intent, reply_text[:30], result.source)
            if intent == "extend":
                assert result.circuit is None or result.source == "ai"  # never swaps in a stored circuit


# ---- the AI may decline; provider hiccups are retried ----------------------------------------------------------


def test_the_ai_can_decline_a_request_that_is_not_a_circuit():
    ai = MockAIValidator(generations=['{"unsupported": "a sandwich is not a logic circuit"}'])
    result = run(make(ai).generate(None, "half adder but also a sandwich", intent="describe"))
    assert not result.success and result.circuit is None and "sandwich" in result.notice
    assert len(ai.generation_prompts) == 1  # no retries, and no stored circuit shown instead


def test_a_provider_hiccup_is_retried_not_fatal():
    from app.ai.validator import AIValidationError

    class Flaky(MockAIValidator):
        calls = 0

        async def complete_json(self, system, user):
            Flaky.calls += 1
            if Flaky.calls == 1:
                raise AIValidationError("unavailable", "The AI service refused or failed the request.")
            return await super().complete_json(system, user)

    ai = Flaky(generations=[reply(golden("half_adder"), HALF_ADDER_SPEC)])
    result = run(make(ai).generate(None, "half adder", intent="describe"))
    assert result.success and result.source == "ai" and result.attempts == 2


def test_a_real_configuration_error_is_not_retried():
    from app.ai.validator import AIValidationError

    ai = MockAIValidator(error=AIValidationError("auth", "The AI is misconfigured (authentication failed)."))
    result = run(make(ai).generate(None, "quantum teleporter", intent="describe"))
    assert not result.success and "authentication" in result.notice and len(ai.generation_prompts) == 1
