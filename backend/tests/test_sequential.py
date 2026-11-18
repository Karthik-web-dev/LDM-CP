"""Flip-flop ICs (7476, 7474) and the sequential exercises."""

import pytest

from app.ai.client import MockAIValidator
from app.config import Settings
from app.models.circuit import Circuit
from app.services.task_repository import TaskRepository
from app.services.validation_service import ValidationService


def service() -> ValidationService:
    return ValidationService(MockAIValidator(), Settings(ai_provider="mock"))


def task(task_id: str):
    found = TaskRepository().get(task_id)
    assert found is not None, task_id
    return found


def conn(src, dst, pin=None, out=None):
    c = {"from": src, "to": dst}
    if pin is not None:
        c["input_index"] = pin
    if out is not None:
        c["output_index"] = out
    return c


def vcc_to(ic, pins):
    return [conn("vcc", ic, p) for p in pins]


def circuit(inputs, gates, outputs, connections) -> Circuit:
    return Circuit.model_validate(
        {
            "version": 1,
            "inputs": [{"id": f"in_{n}", "label": n} for n in inputs],
            "gates": gates,
            "outputs": [{"id": f"out_{n}", "label": n} for n in outputs],
            "connections": connections,
        }
    )


def ripple_counter(clock_from_qbar: bool) -> Circuit:
    # 7476 pins: 0 1CLK, 1 /1PRE, 2 /1CLR, 3 1J, 4 1K, 5 2CLK, 6 /2PRE, 7 /2CLR, 8 2J, 9 2K. Outputs: 0 1Q, 1 /1Q, 2 2Q, 3 /2Q.
    return circuit(
        ["CLK"],
        [{"id": "ff", "type": "7476", "inputs": 10}, {"id": "vcc", "type": "VCC", "inputs": 0}],
        ["Q1", "Q0"],
        [conn("in_CLK", "ff", 0), conn("ff", "ff", 5, out=1 if clock_from_qbar else 0)]
        + vcc_to("ff", [1, 2, 3, 4, 6, 7, 8, 9])
        + [conn("ff", "out_Q0", out=0), conn("ff", "out_Q1", out=2)],
    )


def sync_updown() -> Circuit:
    return circuit(
        ["CLK", "M"],
        [{"id": "ff", "type": "7476", "inputs": 10}, {"id": "vcc", "type": "VCC", "inputs": 0}, {"id": "x", "type": "XOR", "inputs": 2}],
        ["Q1", "Q0"],
        [conn("in_CLK", "ff", 0), conn("in_CLK", "ff", 5)]
        + vcc_to("ff", [1, 2, 3, 4, 6, 7])
        + [conn("ff", "x", 0, out=0), conn("in_M", "x", 1), conn("x", "ff", 8), conn("x", "ff", 9)]
        + [conn("ff", "out_Q0", out=0), conn("ff", "out_Q1", out=2)],
    )


def shift_register() -> Circuit:
    # 7474 pins: 0 1D, 1 1CLK, 2 /1PRE, 3 /1CLR, 4 2D, 5 2CLK, 6 /2PRE, 7 /2CLR. Outputs: 0 1Q, 1 /1Q, 2 2Q, 3 /2Q.
    gates = [{"id": "a", "type": "7474", "inputs": 8}, {"id": "b", "type": "7474", "inputs": 8}, {"id": "vcc", "type": "VCC", "inputs": 0}]
    wires = [conn("in_DIN", "a", 0), conn("a", "a", 4, out=0), conn("a", "b", 0, out=2), conn("b", "b", 4, out=0)]
    for ic in ("a", "b"):
        wires += [conn("in_CLK", ic, 1), conn("in_CLK", ic, 5)] + [conn("vcc", ic, p) for p in (2, 3, 6, 7)]
    wires += [conn("a", "out_Q0", out=0), conn("a", "out_Q1", out=2), conn("b", "out_Q2", out=0), conn("b", "out_Q3", out=2)]
    return circuit(["CLK", "DIN"], gates, ["Q3", "Q2", "Q1", "Q0"], wires)


CASES = [
    ("async_up_counter_2bit", lambda: ripple_counter(False)),
    ("async_down_counter_2bit", lambda: ripple_counter(True)),
    ("sync_updown_counter_2bit", sync_updown),
    ("shift_register_4bit", shift_register),
]


@pytest.mark.parametrize("task_id,build", CASES)
def test_reference_circuits_pass_their_exercise(task_id, build):
    det = service().analyze(task(task_id), build())
    assert det.errors == [], [e.message for e in det.errors]
    assert det.sequence is not None
    assert det.sequence.all_match, [r for r in det.sequence.rows if not r.ok]
    assert det.equivalent_to_expected


def test_wrong_clock_source_is_caught_on_the_first_bad_pulse():
    # Using Q instead of /Q makes an up counter; the down-counter exercise must fail.
    det = service().analyze(task("async_down_counter_2bit"), ripple_counter(False))
    assert det.sequence is not None and not det.sequence.all_match
    assert det.sequence.first_mismatch == 1
    assert det.sequence.rows[0].actual == {"Q1": 0, "Q0": 1}


def test_unconnected_flip_flop_pins_are_reported():
    broken = circuit(
        ["CLK"],
        [{"id": "ff", "type": "7476", "inputs": 10}],
        ["Q1", "Q0"],
        [conn("in_CLK", "ff", 0), conn("ff", "out_Q0", out=0), conn("ff", "out_Q1", out=2)],
    )
    det = service().analyze(task("async_up_counter_2bit"), broken)
    assert any(e.type.value == "MISSING_INPUT" for e in det.errors)
    assert det.sequence is None


def test_missing_clock_input_is_reported():
    c = ripple_counter(False)
    c.inputs[0].label = "NOTCLK"
    det = service().analyze(task("async_up_counter_2bit"), c)
    assert any(e.type.value == "MISSING_TASK_INPUT" for e in det.errors)


def test_flip_flops_are_rejected_for_combinational_exercises():
    det = service().analyze(task("and_gate_001"), ripple_counter(False))
    assert any(e.type.value == "SEQUENTIAL_CIRCUIT" for e in det.errors)


def test_asynchronous_clear_overrides_the_clock():
    # /CLR of both flip-flops held low: the counter never leaves 00.
    c = ripple_counter(False)
    c.connections = [x for x in c.connections if not (x.to == "ff" and x.input_index in (2, 7))]
    c.gates.append(type(c.gates[0]).model_validate({"id": "gnd", "type": "GND", "inputs": 0}))
    c.connections += [type(c.connections[0]).model_validate(conn("gnd", "ff", p)) for p in (2, 7)]
    det = service().analyze(task("async_up_counter_2bit"), c)
    assert det.sequence is not None
    assert all(row.actual == {"Q1": 0, "Q0": 0} for row in det.sequence.rows)
    assert not det.sequence.all_match


def test_ai_payload_carries_the_sequence_trace():
    svc = service()
    t = task("async_up_counter_2bit")
    c = ripple_counter(True)
    det = svc.analyze(t, c)
    payload = svc.build_ai_payload(t, c, det)
    trace = payload["deterministic_analysis"]["sequence_trace"]
    assert trace[0]["expected_outputs"] == {"Q1": 0, "Q0": 1}
    assert payload["task"]["expected_outputs"]["defined_by"] == "sequence"


# ---- gate-level feedback: latches ------------------------------------------------------------------------------


def latch(gate_type: str = "NAND") -> Circuit:
    return circuit(
        ["S", "R"],
        [{"id": "q", "type": gate_type, "inputs": 2}, {"id": "qn", "type": gate_type, "inputs": 2}],
        ["Q", "Qn"],
        [conn("in_S", "q", 0), conn("qn", "q", 1), conn("in_R", "qn", 0), conn("q", "qn", 1), conn("q", "out_Q"), conn("qn", "out_Qn")],
    )


def test_cross_coupled_nand_gates_pass_the_sr_latch_exercise():
    det = service().analyze(task("sr_latch_nand"), latch())
    assert det.errors == [] and det.sequence is not None and det.sequence.clock is None
    assert det.sequence.all_match, [r for r in det.sequence.rows if not r.ok]


def test_the_wrong_gate_type_is_a_wrong_latch_not_an_error():
    det = service().analyze(task("sr_latch_nand"), latch("NOR"))  # NOR latch has active-high inputs
    assert det.errors == [] and det.sequence is not None and not det.sequence.all_match


def test_the_clocked_sr_flip_flop_holds_when_clk_is_low():
    nand = lambda gid: {"id": gid, "type": "NAND", "inputs": 2}  # noqa: E731
    flip_flop = circuit(
        ["S", "R", "CLK"],
        [nand("gs"), nand("gr"), nand("q"), nand("qn")],
        ["Q", "Qn"],
        [
            conn("in_S", "gs", 0), conn("in_CLK", "gs", 1), conn("in_R", "gr", 0), conn("in_CLK", "gr", 1),
            conn("gs", "q", 0), conn("qn", "q", 1), conn("gr", "qn", 0), conn("q", "qn", 1),
            conn("q", "out_Q"), conn("qn", "out_Qn"),
        ],
    )
    det = service().analyze(task("sr_flipflop_nand"), flip_flop)
    assert det.errors == [] and det.sequence.all_match, [r for r in det.sequence.rows if not r.ok]


def test_a_circuit_that_never_settles_is_reported():
    ring = circuit(["S", "R"], [{"id": "n", "type": "NOT", "inputs": 1}], ["Q", "Qn"], [conn("n", "n", 0), conn("n", "out_Q"), conn("n", "out_Qn")])
    det = service().analyze(task("sr_latch_nand"), ring)
    assert [e.type.value for e in det.errors] == ["UNSTABLE_CIRCUIT"] and det.sequence is None


def test_feedback_is_still_an_error_for_combinational_exercises():
    looped = circuit(
        ["A", "B"], [{"id": "g", "type": "AND", "inputs": 2}], ["Y"],
        [conn("in_A", "g", 0), conn("g", "g", 1), conn("g", "out_Y")],
    )
    det = service().analyze(task("and_gate_001"), looped)
    assert any(e.type.value == "CYCLE_DETECTED" for e in det.errors)


def test_a_stray_gate_with_an_unwired_pin_does_not_crash_the_check():
    """Such a gate is only a warning (it feeds nothing), so the simulator must cope with it."""
    stray = latch()
    stray.gates.append(type(stray.gates[0]).model_validate({"id": "stray", "type": "NAND", "inputs": 2}))
    stray.connections.append(type(stray.connections[0]).model_validate(conn("in_S", "stray", 0)))
    det = service().analyze(task("sr_latch_nand"), stray)
    assert det.errors == [] and det.sequence is not None and det.sequence.all_match
    assert any(w.type.value == "DANGLING_GATE" for w in det.warnings)
