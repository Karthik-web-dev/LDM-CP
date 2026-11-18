"""Generate the reference (golden) circuit of every built-in exercise.

    cd backend && ../venv/Scripts/python.exe -m app.tools.build_golden

Most exercises are built from the target itself: the simplified Boolean equations become a gate-level
circuit. Exercises that name specific ICs (74153, 74138, 7476, 7474) use a hand-wired netlist below.
Every circuit is laid out automatically and written to ``app/data/golden/<task id>.json``.
Run ``python -m app.tools.backtest`` afterwards to prove they all pass.
"""

import json
from typing import Callable

from app.analysis.expected_function import build_expected
from app.analysis.expression_parser import parse_expression
from app.generator.circuit_builder import NetBuilder, circuit_from_expressions
from app.generator.layout import apply_layout
from app.models.task import Task
from app.services.golden_repository import GOLDEN_DIR
from app.services.task_repository import TaskRepository

# ---- hand-wired IC circuits ------------------------------------------------------------------

# 74153 pins: 0 A, 1 B, 2 /1G, 3..6 1C0..1C3, 7 /2G, 8..11 2C0..2C3. Outputs: 0 1Y, 1 2Y.
# 74138 pins: 0 A, 1 B, 2 C, 3 G1, 4 /G2A, 5 /G2B. Outputs /Y0../Y7.
# 7476 pins: 0 1CLK, 1 /1PRE, 2 /1CLR, 3 1J, 4 1K, 5 2CLK, 6 /2PRE, 7 /2CLR, 8 2J, 9 2K. Outputs: 1Q, /1Q, 2Q, /2Q.
# 7474 pins: 0 1D, 1 1CLK, 2 /1PRE, 3 /1CLR, 4 2D, 5 2CLK, 6 /2PRE, 7 /2CLR. Outputs: 1Q, /1Q, 2Q, /2Q.


def full_adder_74153() -> dict:
    """S and Cout as 8:1 muxes, each made from the two 4:1 halves of a 74153.

    The shared selects are (B, Cin); the third select bit A enables half 1 (A = 0) or half 2 (A = 1).
    """
    net = NetBuilder()
    a, b, cin = net.add_input("A"), net.add_input("B"), net.add_input("Cin")
    not_a = net.add_gate("NOT", 1)
    net.wire(a, not_a, 0)

    def mux8(label: str, low: list[int], high: list[int]) -> None:
        ic = net.add_gate("74153", 12)
        net.wire(cin, ic, 0)  # A select (LSB)
        net.wire(b, ic, 1)  # B select (MSB)
        net.wire(a, ic, 2)  # /1G low when A = 0
        net.wire(not_a, ic, 7)  # /2G low when A = 1
        for k in range(4):
            net.wire(net.constant(bool(low[k])), ic, 3 + k)
            net.wire(net.constant(bool(high[k])), ic, 8 + k)
        either = net.add_gate("OR", 2)
        net.wire(ic, either, 0, 0)
        net.wire(ic, either, 1, 1)
        net.add_output(label, either)

    # index = 2*B + Cin
    mux8("S", low=[0, 1, 1, 0], high=[1, 0, 0, 1])
    mux8("Cout", low=[0, 0, 0, 1], high=[0, 1, 1, 1])
    return net.build()


def comparator_74138() -> dict:
    """2-bit comparator from two 74138s used as a 4:16 decoder (A1 picks which one is enabled)."""
    net = NetBuilder()
    a1, a0, b1, b0 = (net.add_input(n) for n in ("A1", "A0", "B1", "B0"))
    vcc, gnd = net.constant(True), net.constant(False)
    low, high = net.add_gate("74138", 6), net.add_gate("74138", 6)
    for ic in (low, high):
        net.wire(a0, ic, 0)  # A = A0
        net.wire(b0, ic, 1)  # B = B0
        net.wire(b1, ic, 2)  # C = B1, so output index = B1*4 + B0*2 + A0
    net.wire(vcc, low, 3)  # G1 = 1, /G2A = A1: enabled when A1 = 0
    net.wire(a1, low, 4)
    net.wire(gnd, low, 5)
    net.wire(a1, high, 3)  # G1 = A1: enabled when A1 = 1
    net.wire(gnd, high, 4)
    net.wire(gnd, high, 5)

    for label, wanted in (
        ("Agt", lambda a, b: a > b),
        ("Aeq", lambda a, b: a == b),
        ("Alt", lambda a, b: a < b),
    ):
        picks = [
            (high if a >> 1 else low, (b >> 1) * 4 + (b & 1) * 2 + (a & 1))
            for a in range(4) for b in range(4) if wanted(a, b)
        ]
        # The decoder outputs are active low, so NAND of the wanted outputs is their OR.
        nand = net.add_gate("NAND", len(picks))
        for pin, (ic, out) in enumerate(picks):
            net.wire(ic, nand, pin, out)
        net.add_output(label, nand)
    return net.build()


def sr_latch_nand() -> dict:
    """Two cross-coupled NAND gates: Q = NAND(S, Qn), Qn = NAND(R, Q)."""
    net = NetBuilder()
    s, r = net.add_input("S"), net.add_input("R")
    q, qn = net.add_gate("NAND", 2), net.add_gate("NAND", 2)
    net.wire(s, q, 0)
    net.wire(qn, q, 1)
    net.wire(r, qn, 0)
    net.wire(q, qn, 1)
    net.add_output("Q", q)
    net.add_output("Qn", qn)
    return net.build()


def sr_flipflop_nand() -> dict:
    """Gated SR flip-flop: NAND(S, CLK) and NAND(R, CLK) drive a cross-coupled NAND latch."""
    net = NetBuilder()
    s, r, clk = net.add_input("S"), net.add_input("R"), net.add_input("CLK")
    gate_s, gate_r = net.add_gate("NAND", 2), net.add_gate("NAND", 2)
    q, qn = net.add_gate("NAND", 2), net.add_gate("NAND", 2)
    net.wire(s, gate_s, 0)
    net.wire(clk, gate_s, 1)
    net.wire(r, gate_r, 0)
    net.wire(clk, gate_r, 1)
    net.wire(gate_s, q, 0)
    net.wire(qn, q, 1)
    net.wire(gate_r, qn, 0)
    net.wire(q, qn, 1)
    net.add_output("Q", q)
    net.add_output("Qn", qn)
    return net.build()


def ripple_counter(count_down: bool) -> dict:
    net = NetBuilder()
    clk = net.add_input("CLK")
    ff, vcc = net.add_gate("7476", 10), net.constant(True)
    net.wire(clk, ff, 0)
    net.wire_pins(vcc, ff, [1, 2, 3, 4, 6, 7, 8, 9])
    net.wire(ff, ff, 5, 1 if count_down else 0)  # 2CLK from /1Q (down) or 1Q (up)
    net.add_output("Q1", ff, 2)
    net.add_output("Q0", ff, 0)
    return net.build()


def sync_updown_counter() -> dict:
    net = NetBuilder()
    clk, m = net.add_input("CLK"), net.add_input("M")
    ff, vcc, xor = net.add_gate("7476", 10), net.constant(True), net.add_gate("XOR", 2)
    net.wire(clk, ff, 0)
    net.wire(clk, ff, 5)
    net.wire_pins(vcc, ff, [1, 2, 3, 4, 6, 7])
    net.wire(ff, xor, 0, 0)  # Q0 XOR M: toggle the high bit when counting
    net.wire(m, xor, 1)
    net.wire_pins(xor, ff, [8, 9])
    net.add_output("Q1", ff, 2)
    net.add_output("Q0", ff, 0)
    return net.build()


def shift_register() -> dict:
    net = NetBuilder()
    clk, din = net.add_input("CLK"), net.add_input("DIN")
    first, second, vcc = net.add_gate("7474", 8), net.add_gate("7474", 8), net.constant(True)
    net.wire(din, first, 0)
    net.wire(first, first, 4, 0)  # Q0 -> D of the next stage
    net.wire(first, second, 0, 2)  # Q1 -> D
    net.wire(second, second, 4, 0)  # Q2 -> D
    for ic in (first, second):
        net.wire_pins(clk, ic, [1, 5])
        net.wire_pins(vcc, ic, [2, 3, 6, 7])
    net.add_output("Q3", second, 2)
    net.add_output("Q2", second, 0)
    net.add_output("Q1", first, 2)
    net.add_output("Q0", first, 0)
    return net.build()


def xor_from_and_or_not() -> dict:
    """The exercise asks for AND, OR and NOT only, so spell XOR out as (A AND NOT B) OR (NOT A AND B)."""
    expr = parse_expression("(A AND NOT B) OR (NOT A AND B)", known_variables=["A", "B"])
    return circuit_from_expressions(["A", "B"], {"Y": expr})


SPECIAL: dict[str, Callable[[], dict]] = {
    "xor_from_basics": xor_from_and_or_not,
    "full_adder_mux_74153": full_adder_74153,
    "comparator_2bit_74138": comparator_74138,
    "async_up_counter_2bit": lambda: ripple_counter(False),
    "async_down_counter_2bit": lambda: ripple_counter(True),
    "sync_updown_counter_2bit": sync_updown_counter,
    "shift_register_4bit": shift_register,
    "sr_latch_nand": sr_latch_nand,
    "sr_flipflop_nand": sr_flipflop_nand,
}


def circuit_from_task(task: Task) -> dict:
    """Gate-level circuit from the exercise's own (simplified) equations."""
    outputs, problems = build_expected(task)
    if problems:
        raise ValueError("; ".join(problems))
    return circuit_from_expressions(list(task.inputs), {o.label: o.expression for o in outputs})


def golden_circuit(task: Task) -> dict:
    build = SPECIAL.get(task.id)
    circuit = build() if build else circuit_from_task(task)
    return apply_layout(circuit)


def main() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for task in TaskRepository().list():
        payload = {"task_id": task.id, "title": task.title, "source": "reference", "circuit": golden_circuit(task)}
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        (GOLDEN_DIR / f"{task.id}.json").write_text(text + chr(10), encoding="utf-8")
        print(f"wrote {task.id}")


if __name__ == "__main__":
    main()
