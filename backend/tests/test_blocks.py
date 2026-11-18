"""Multi-output blocks: MUX, DEMUX, decoder, encoder."""

from itertools import product

import pytest

from app.analysis.evaluator import evaluate
from app.analysis.expression_generator import generate_expressions
from app.analysis.structural_validator import validate_structure
from app.config import Limits
from app.models.circuit import Circuit


def build(block: str, n_in: int, n_out: int) -> Circuit:
    """Inputs I0..I(n-1) wired to the block's pins in order; one output per block output pin."""
    conns = [{"from": f"in{i}", "to": "blk", "input_index": i} for i in range(n_in)]
    conns += [{"from": "blk", "to": f"out{k}", "output_index": k} for k in range(n_out)]
    return Circuit.model_validate(
        {
            "version": 1,
            "inputs": [{"id": f"in{i}", "label": f"I{i}"} for i in range(n_in)],
            "gates": [{"id": "blk", "type": block, "inputs": n_in}],
            "outputs": [{"id": f"out{k}", "label": f"Y{k}"} for k in range(n_out)],
            "connections": conns,
        }
    )


def truth(circuit: Circuit):
    report = validate_structure(circuit, Limits())
    assert not report.errors, [e.message for e in report.errors]
    exprs = generate_expressions(report.graph, report.order)
    labels = [i.label for i in circuit.inputs]
    for values in product([False, True], repeat=len(labels)):
        env = dict(zip(labels, values))
        yield values, [evaluate(exprs[f"out{k}"], env) for k in range(len(exprs))]


def bits(values) -> int:
    n = 0
    for v in values:
        n = (n << 1) | int(v)
    return n


@pytest.mark.parametrize("block,n_data,n_sel", [("MUX2", 2, 1), ("MUX4", 4, 2)])
def test_mux_selects_the_addressed_input(block, n_data, n_sel):
    for values, (y,) in truth(build(block, n_data + n_sel, 1)):
        data, sel = values[:n_data], bits(values[n_data:])
        assert y == data[sel]


@pytest.mark.parametrize("block,n_out,n_sel", [("DEMUX2", 2, 1), ("DEMUX4", 4, 2)])
def test_demux_routes_data_to_the_addressed_output(block, n_out, n_sel):
    for values, outs in truth(build(block, 1 + n_sel, n_out)):
        d, sel = values[0], bits(values[1:])
        assert outs == [d and k == sel for k in range(n_out)]


@pytest.mark.parametrize("block,n_in", [("DECODER2", 2), ("DECODER3", 3)])
def test_decoder_is_one_hot(block, n_in):
    for values, outs in truth(build(block, n_in, 2**n_in)):
        assert outs == [k == bits(values) for k in range(2**n_in)]


@pytest.mark.parametrize("block,n_in,n_out", [("ENCODER4", 4, 2), ("ENCODER8", 8, 3)])
def test_encoder_returns_the_index_of_the_active_input(block, n_in, n_out):
    for values, outs in truth(build(block, n_in, n_out)):
        if sum(values) != 1:
            continue  # a plain encoder is only defined for exactly one active input
        assert bits(outs) == values.index(True)


def test_output_index_out_of_range_is_rejected():
    circuit = build("DEMUX2", 2, 2)
    circuit.connections[-1].output_index = 5
    report = validate_structure(circuit, Limits())
    assert any(i.type.value == "INVALID_CONNECTION" for i in report.errors)


def test_single_output_gates_still_accept_output_index_zero():
    circuit = Circuit.model_validate(
        {
            "version": 1,
            "inputs": [{"id": "a", "label": "A"}],
            "gates": [{"id": "g", "type": "NOT"}],
            "outputs": [{"id": "o", "label": "Y"}],
            "connections": [{"from": "a", "to": "g"}, {"from": "g", "to": "o", "output_index": 0}],
        }
    )
    assert not validate_structure(circuit, Limits()).errors
