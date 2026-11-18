"""Central gate registry: arity rules and Boolean semantics for every supported gate type.

To add a gate, add one ``GateDefinition`` here (plus an AST operator in ``boolean_ast`` if it
needs a new one). Nothing else in the analysis pipeline is gate-specific.
"""

from dataclasses import dataclass
from typing import Callable

from app.analysis.boolean_ast import And, BooleanExpression, Const, Nand, Nor, Not, Or, Xnor, Xor


def _literal(sel: BooleanExpression, bit: int) -> BooleanExpression:
    return sel if bit else Not(sel)


def _minterm(selects: list[BooleanExpression], value: int) -> list[BooleanExpression]:
    """Literals that are all true exactly when ``selects`` (MSB first) encode ``value``."""
    n = len(selects)
    return [_literal(s, (value >> (n - 1 - i)) & 1) for i, s in enumerate(selects)]


def _and(terms: list[BooleanExpression]) -> BooleanExpression:
    return terms[0] if len(terms) == 1 else And(tuple(terms))


def _or(terms: list[BooleanExpression]) -> BooleanExpression:
    return terms[0] if len(terms) == 1 else Or(tuple(terms))


def _mux_outputs(n_data: int):
    def build(args: list[BooleanExpression]) -> list[BooleanExpression]:
        data, selects = args[:n_data], args[n_data:]
        return [_or([_and([data[k], *_minterm(selects, k)]) for k in range(n_data)])]

    return build


def _demux_outputs(n_out: int):
    def build(args: list[BooleanExpression]) -> list[BooleanExpression]:
        data, selects = args[0], args[1:]
        return [_and([data, *_minterm(selects, k)]) for k in range(n_out)]

    return build


def _decoder_outputs(n_out: int):
    def build(args: list[BooleanExpression]) -> list[BooleanExpression]:
        return [_and(_minterm(args, k)) for k in range(n_out)]

    return build


def _encoder_outputs(n_in: int):
    """Plain (non-priority) encoder: output bit b is the OR of every input whose index has bit b set.

    Correct when exactly one input is 1, the normal use of an encoder.
    """
    n_out = n_in.bit_length() - 1

    def build(args: list[BooleanExpression]) -> list[BooleanExpression]:
        outs = []
        for bit in range(n_out - 1, -1, -1):  # MSB first
            outs.append(_or([args[k] for k in range(n_in) if (k >> bit) & 1]))
        return outs

    return build


def _ttl_74138(args: list[BooleanExpression]) -> list[BooleanExpression]:
    """74138 3-to-8 decoder. Pins: A, B, C, G1, /G2A, /G2B. Outputs /Y0../Y7 are active low."""
    a, b, c, g1, g2a, g2b = args
    enable = And((g1, Not(g2a), Not(g2b)))
    return [Not(And((enable, *_minterm([c, b, a], k)))) for k in range(8)]


def _ttl_74153(args: list[BooleanExpression]) -> list[BooleanExpression]:
    """74153 dual 4-to-1 multiplexer. Pins: A, B, /1G, 1C0..1C3, /2G, 2C0..2C3. Outputs 1Y, 2Y.

    The select inputs A (LSB) and B (MSB) are shared. Each half is enabled by its active-low strobe.
    """
    a, b = args[0], args[1]
    outputs = []
    for base in (2, 7):
        strobe, data = args[base], args[base + 1 : base + 5]
        picked = _or([_and([data[k], *_minterm([b, a], k)]) for k in range(4)])
        outputs.append(And((Not(strobe), picked)))
    return outputs


def _no_combinational_function(args: list[BooleanExpression]) -> BooleanExpression:
    raise NotImplementedError("a flip-flop has no combinational function; its state is simulated per clock pulse")


def _flip_flop_ic(type_: str, spec: "SequentialSpec", description: str) -> "GateDefinition":
    n_in = spec.ffs * spec.stride
    return GateDefinition(
        type_, n_in, n_in, n_in, _no_combinational_function, description, n_outputs=spec.ffs * 2, sequential=spec
    )


def _block(type_: str, n_in: int, n_out: int, builder, description: str) -> "GateDefinition":
    return GateDefinition(
        type_, n_in, n_in, n_in, lambda a, b=builder: b(a)[0], description, n_outputs=n_out, build_outputs=builder
    )


@dataclass(frozen=True)
class SequentialSpec:
    """Pin layout of a flip-flop IC. Pin indices are offsets inside each flip-flop's block of pins."""

    kind: str  # "jk" or "d"
    ffs: int  # flip-flops in the package
    stride: int  # input pins per flip-flop
    edge: str  # active clock edge: "falling" or "rising"
    clk: int
    pre: int  # active-low asynchronous preset
    clr: int  # active-low asynchronous clear (wins over preset)
    j: int | None = None
    k: int | None = None
    d: int | None = None


@dataclass(frozen=True)
class GateDefinition:
    type: str
    min_inputs: int
    max_inputs: int | None
    default_inputs: int
    build: Callable[[list[BooleanExpression]], BooleanExpression]
    description: str
    # Multi-output blocks (MUX, DEMUX, decoder, encoder). ``build_outputs`` maps the input
    # expressions to one expression per output pin; ``build`` then returns output 0.
    n_outputs: int = 1
    sequential: SequentialSpec | None = None
    build_outputs: Callable[[list[BooleanExpression]], list[BooleanExpression]] | None = None

    def build_all(self, args: list[BooleanExpression]) -> list[BooleanExpression]:
        if self.build_outputs is not None:
            return self.build_outputs(args)
        return [self.build(args)]

    def accepts(self, n: int) -> bool:
        return n >= self.min_inputs and (self.max_inputs is None or n <= self.max_inputs)

    def arity_text(self) -> str:
        if self.max_inputs == self.min_inputs:
            return f"exactly {self.min_inputs}"
        if self.max_inputs is None:
            return f"at least {self.min_inputs}"
        return f"between {self.min_inputs} and {self.max_inputs}"


def _nary(op: type) -> Callable[[list[BooleanExpression]], BooleanExpression]:
    return lambda args: op(tuple(args))


GATE_DEFINITIONS: dict[str, GateDefinition] = {
    d.type: d
    for d in [
        GateDefinition("AND", 2, None, 2, _nary(And), "Outputs 1 only when all inputs are 1."),
        GateDefinition("OR", 2, None, 2, _nary(Or), "Outputs 1 when at least one input is 1."),
        GateDefinition("NOT", 1, 1, 1, lambda a: Not(a[0]), "Outputs the inverse of its input."),
        GateDefinition("NAND", 2, None, 2, _nary(Nand), "Outputs 0 only when all inputs are 1."),
        GateDefinition("NOR", 2, None, 2, _nary(Nor), "Outputs 1 only when all inputs are 0."),
        GateDefinition("XOR", 2, None, 2, _nary(Xor), "Outputs 1 when an odd number of inputs are 1."),
        GateDefinition("XNOR", 2, None, 2, _nary(Xnor), "Outputs 1 when an even number of inputs are 1."),
        # A buffer passes its input through unchanged, so it adds no node to the expression.
        GateDefinition("BUFFER", 1, 1, 1, lambda a: a[0], "Outputs its input unchanged."),
        # Constant sources: tie unused pins, enables, presets and clears to a fixed level.
        GateDefinition("VCC", 0, 0, 0, lambda a: Const(True), "Constant logic 1 (VCC)."),
        GateDefinition("GND", 0, 0, 0, lambda a: Const(False), "Constant logic 0 (GND)."),
        # 74xx integrated circuits (pin order as documented in CIRCUIT_FORMAT.md).
        _block("74138", 6, 8, _ttl_74138, "74138 3-to-8 decoder. Pins: A, B, C, G1, /G2A, /G2B. Outputs /Y0../Y7 (active low)."),
        _flip_flop_ic(
            "7476",
            SequentialSpec("jk", 2, 5, "falling", clk=0, pre=1, clr=2, j=3, k=4),
            "7476 dual JK flip-flop, falling-edge triggered, active-low preset and clear. "
            "Pins: 1CLK, /1PRE, /1CLR, 1J, 1K, 2CLK, /2PRE, /2CLR, 2J, 2K. Outputs: 1Q, /1Q, 2Q, /2Q.",
        ),
        _flip_flop_ic(
            "7474",
            SequentialSpec("d", 2, 4, "rising", clk=1, pre=2, clr=3, d=0),
            "7474 dual D flip-flop, rising-edge triggered, active-low preset and clear. "
            "Pins: 1D, 1CLK, /1PRE, /1CLR, 2D, 2CLK, /2PRE, /2CLR. Outputs: 1Q, /1Q, 2Q, /2Q.",
        ),
        _block("74153", 12, 2, _ttl_74153, "74153 dual 4-to-1 multiplexer. Pins: A, B, /1G, 1C0..1C3, /2G, 2C0..2C3. Outputs 1Y, 2Y."),
        # Multi-output / data-routing blocks. Pin order is documented in CIRCUIT_FORMAT.md.
        _block("MUX2", 3, 1, _mux_outputs(2), "2-to-1 multiplexer. Pins: D0, D1, S. Y = D(S)."),
        _block("MUX4", 6, 1, _mux_outputs(4), "4-to-1 multiplexer. Pins: D0..D3, S1, S0. Y = D(S1S0)."),
        _block("DEMUX2", 2, 2, _demux_outputs(2), "1-to-2 demultiplexer. Pins: D, S. Y(S) = D, other output 0."),
        _block("DEMUX4", 3, 4, _demux_outputs(4), "1-to-4 demultiplexer. Pins: D, S1, S0. Y(S1S0) = D, others 0."),
        _block("DECODER2", 2, 4, _decoder_outputs(4), "2-to-4 decoder. Pins: A1, A0. Y(A1A0) = 1."),
        _block("DECODER3", 3, 8, _decoder_outputs(8), "3-to-8 decoder. Pins: A2, A1, A0. Y(A2A1A0) = 1."),
        _block("ENCODER4", 4, 2, _encoder_outputs(4), "4-to-2 encoder. Pins: D0..D3. Outputs A1, A0 (assumes one input high)."),
        _block("ENCODER8", 8, 3, _encoder_outputs(8), "8-to-3 encoder. Pins: D0..D7. Outputs A2, A1, A0 (assumes one input high)."),
    ]
}

GATE_ALIASES = {"INV": "NOT", "INVERTER": "NOT", "BUF": "BUFFER"}


def normalize_gate_type(gate_type: str) -> str:
    t = gate_type.strip().upper()
    return GATE_ALIASES.get(t, t)


def get_gate_definition(gate_type: str) -> GateDefinition | None:
    return GATE_DEFINITIONS.get(normalize_gate_type(gate_type))
