"""VCC/GND constants and the 74138 / 74153 integrated circuits."""

from itertools import product

from app.analysis.evaluator import evaluate
from app.analysis.expression_generator import generate_expressions
from app.analysis.structural_validator import validate_structure
from app.config import Limits
from app.models.circuit import Circuit


def table(inputs, gates, outputs, connections):
    """Evaluate every output for every input assignment. ``outputs`` are labels."""
    circuit = Circuit.model_validate(
        {
            "version": 1,
            "inputs": [{"id": f"in_{n}", "label": n} for n in inputs],
            "gates": gates,
            "outputs": [{"id": f"out_{n}", "label": n} for n in outputs],
            "connections": connections,
        }
    )
    report = validate_structure(circuit, Limits())
    assert not report.errors, [e.message for e in report.errors]
    exprs = generate_expressions(report.graph, report.order)
    for values in product([False, True], repeat=len(inputs)):
        env = dict(zip(inputs, values))
        yield env, {n: evaluate(exprs[f"out_{n}"], env) for n in outputs}


def test_vcc_and_gnd_are_constants():
    rows = list(
        table(
            ["A"],
            [{"id": "v", "type": "VCC"}, {"id": "g", "type": "GND"}, {"id": "and1", "type": "AND", "inputs": 2}, {"id": "or1", "type": "OR", "inputs": 2}],
            ["P", "Q"],
            [
                {"from": "in_A", "to": "and1", "input_index": 0}, {"from": "v", "to": "and1", "input_index": 1},
                {"from": "in_A", "to": "or1", "input_index": 0}, {"from": "g", "to": "or1", "input_index": 1},
                {"from": "and1", "to": "out_P"}, {"from": "or1", "to": "out_Q"},
            ],
        )
    )
    for env, out in rows:  # A AND 1 = A and A OR 0 = A
        assert out == {"P": env["A"], "Q": env["A"]}


def test_74138_is_an_active_low_decoder_with_three_enables():
    names = ["A", "B", "C", "G1", "G2A", "G2B"]
    conns = [{"from": f"in_{n}", "to": "ic", "input_index": i} for i, n in enumerate(names)]
    conns += [{"from": "ic", "to": f"out_Y{k}", "output_index": k} for k in range(8)]
    for env, out in table(names, [{"id": "ic", "type": "74138", "inputs": 6}], [f"Y{k}" for k in range(8)], conns):
        enabled = env["G1"] and not env["G2A"] and not env["G2B"]
        address = env["C"] * 4 + env["B"] * 2 + env["A"]
        for k in range(8):
            assert out[f"Y{k}"] == (not (enabled and k == address))


def test_74153_halves_share_selects_and_have_active_low_strobes():
    names = ["A", "B", "G1", "D10", "D11", "D12", "D13", "G2", "D20", "D21", "D22", "D23"]
    conns = [{"from": f"in_{n}", "to": "ic", "input_index": i} for i, n in enumerate(names)]
    conns += [{"from": "ic", "to": "out_Y1", "output_index": 0}, {"from": "ic", "to": "out_Y2", "output_index": 1}]
    rows = table(names, [{"id": "ic", "type": "74153", "inputs": 12}], ["Y1", "Y2"], conns)
    for n, (env, out) in enumerate(rows):
        if n % 5:  # 4096 rows; every fifth is plenty
            continue
        sel = env["B"] * 2 + env["A"]
        assert out["Y1"] == (not env["G1"] and env[f"D1{sel}"])
        assert out["Y2"] == (not env["G2"] and env[f"D2{sel}"])
