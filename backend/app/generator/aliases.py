"""Ways a person might ask for each built-in circuit, used to find its stored circuit.

Matching is deterministic text matching (see ``app.services.demo_matcher``), never AI. Aliases must be
unique across exercises: a test fails if two exercises claim the same phrase. A phrase is matched when
all its words appear in the request, so keep each one specific.
"""

ALIASES: dict[str, list[str]] = {
    "and_gate_001": ["and gate", "and circuit", "2 input and"],
    "and_or_001": ["and into or", "and or circuit"],
    "nand_from_basics": ["nand from and not", "nand using and not", "nand gate", "nand circuit"],
    "xor_from_basics": ["xor gate", "xor", "exclusive or", "xor from and or not"],
    "majority_3": ["majority", "majority of three", "majority voter", "2 out of 3", "voter"],
    "mux_2to1": ["2 1 mux", "mux 2 1", "2 1 multiplexer", "two to one mux", "mux"],
    "half_adder": ["half adder", "half add"],
    "full_adder": ["full adder", "full add", "adder"],
    "gates_verification": ["verification of logic gates", "verify logic gates", "verify gates", "logic gates", "all gates", "gate verification", "basic gates"],
    "boolean_simplification": ["boolean simplification", "simplify boolean", "boolean algebra", "simplify equation", "simplify with boolean algebra", "simplification"],
    # Converters keep their direction ("A to B"): undirected phrases would be ambiguous between the two.
    "excess3_to_bcd": ["excess 3 to bcd", "excess3 to bcd", "xs3 to bcd"],
    "bcd_to_excess3": ["bcd to excess 3", "bcd to excess3", "bcd to xs3"],
    "full_adder_mux_74153": [
        "full adder using mux", "full adder using multiplexer", "full adder with mux", "full adder 8 1 mux", "full adder 74153",
        "mux full adder", "full adder 4 1 mux", "multiplexer full adder", "74153",
    ],
    "comparator_2bit_74138": ["comparator", "2 bit comparator", "comparator using decoder", "comparator 74138", "decoder comparator", "74138", "3 8 decoder", "decoder"],
    "async_up_counter_2bit": [
        "asynchronous up counter", "async up counter", "ripple counter", "ripple up counter", "up counter", "asynchronous counter",
        "async counter", "counter 7476", "jk counter", "7476",
    ],
    "async_down_counter_2bit": ["asynchronous down counter", "async down counter", "ripple down counter", "down counter"],
    "sync_updown_counter_2bit": [
        "synchronous up down counter", "sync up down counter", "synchronous counter", "sync counter", "up down counter",
        "synchronous up counter", "updown counter",
    ],
    "shift_register_4bit": ["shift register", "4 bit shift register", "sipo", "serial in shift register", "d flip flop shift register", "7474", "shift reg"],
    "sr_latch_nand": ["sr latch", "nand latch", "set reset latch", "latch"],
    "sr_flipflop_nand": ["sr flip flop", "gated sr", "clocked sr", "set reset flip flop"],
}
