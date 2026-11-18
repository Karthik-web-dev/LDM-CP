# Normalized circuit format (version 1)

This is the only representation the backend accepts. It is independent of the editor.

```json
{
  "version": 1,
  "inputs":  [{ "id": "input_1", "label": "A" }, { "id": "input_2", "label": "B" }, { "id": "input_3", "label": "C" }],
  "gates":   [{ "id": "gate_1", "type": "AND", "inputs": 2 }, { "id": "gate_2", "type": "OR", "inputs": 2 }],
  "outputs": [{ "id": "output_1", "label": "Y" }],
  "connections": [
    { "from": "input_1", "to": "gate_1", "input_index": 0 },
    { "from": "input_2", "to": "gate_1", "input_index": 1 },
    { "from": "gate_1",  "to": "gate_2", "input_index": 0 },
    { "from": "input_3", "to": "gate_2", "input_index": 1 },
    { "from": "gate_2",  "to": "output_1" }
  ]
}
```

This circuit analyses to `((A AND B) OR C)`.

## Fields

| Field | Rules |
|---|---|
| `version` | Must be `1`. |
| `id` (all components) | `[A-Za-z0-9_-]{1,64}`, unique across the whole circuit. It identifies the component; nothing else does. |
| `inputs[].label`, `outputs[].label` | Used as the Boolean variable / output name. Must be an identifier (`[A-Za-z_][A-Za-z0-9_]*`, at most 32 characters by default), must not be an operator name (AND, OR, NOT, XOR, NAND, NOR, XNOR), and must be unique among inputs (or among outputs). |
| `gates[].type` | `AND`, `OR`, `NOT`, `NAND`, `NOR`, `XOR`, `XNOR`, `BUFFER` (aliases: `INV`, `INVERTER` → NOT, `BUF` → BUFFER), or a block type listed under *Blocks* below. Case-insensitive. |
| `gates[].inputs` | Number of input pins. Optional: defaults to the type's default (2, or 1 for NOT/BUFFER). AND/OR/NAND/NOR/XOR/XNOR accept 2 or more; NOT/BUFFER exactly 1. |
| `connections[].from` | Id of an input or gate (the driver). |
| `connections[].to` | Id of a gate or output (the sink). |
| `connections[].output_index` | 0-based output pin of the driver. Optional, default 0. Only blocks with several outputs (DEMUX, decoder, encoder) have pins above 0. |
| `connections[].input_index` | 0-based pin on the target gate. Required for gates with more than one pin; optional for single-pin targets (NOT, BUFFER, outputs). |
| `position` (optional, any component) | `{ "x": number, "y": number }`. Display metadata only, ignored by analysis. |

Unknown fields are rejected (HTTP 422), so typos are never silently ignored.

## Semantics

- Each gate input pin and each output must have exactly one driver.
- A driver may fan out to any number of sinks.
- The graph must be acyclic (combinational logic only).
- Multi-input XOR is odd parity and XNOR is even parity, the same as cascading 2-input gates.
- A gate that does not feed any output is reported as `DANGLING_GATE` (a warning) and ignored.

## Structural issue types

| Type | Severity | Meaning |
|---|---|---|
| `MISSING_INPUT` | error (warning on dangling gates) | A gate input pin has no driver |
| `MISSING_OUTPUT` | error | The circuit has no output component |
| `UNDRIVEN_OUTPUT` | error | An output has no driver |
| `UNKNOWN_GATE` | error | Unsupported gate type |
| `INVALID_GATE_ARITY` | error | Wrong number of pins for the gate type |
| `INVALID_CONNECTION` | error | Unknown endpoint, bad pin, output used as a driver, or input used as a sink |
| `MULTIPLE_DRIVER` | error | More than one wire into the same pin or output |
| `CYCLE_DETECTED` | error | Feedback loop; `related` lists the nodes on the cycle |
| `DUPLICATE_ID` / `DUPLICATE_LABEL` / `INVALID_LABEL` | error | Identity problems |
| `LIMIT_EXCEEDED` | error | Circuit or variable count over the configured limits |
| `DANGLING_GATE` | warning | Gate does not affect any output |
| `UNCONNECTED_INPUT` | warning | An input drives nothing |
| `EXPRESSION_TOO_LARGE` | warning | Expression too long to display (correctness is still checked) |
| `OUTPUT_LABEL_MISMATCH`, `MISSING_EXPECTED_OUTPUT`, `EXTRA_OUTPUT`, `MISSING_TASK_INPUT`, `EXTRA_INPUT` | warning | Circuit vs. task naming differences |
| `INVALID_TASK` | error | The task's expected expression does not parse |

## Blocks (multi-pin parts)

Blocks have a fixed number of input pins (`inputs` must match) and, for some, several output pins. Wire a
specific output with `connections[].output_index`. Select and address pins are listed most-significant bit first.

| Type | Input pins (`input_index` 0..) | Output pins (`output_index` 0..) |
|---|---|---|
| `MUX2` | D0, D1, S | Y = D(S) |
| `MUX4` | D0, D1, D2, D3, S1, S0 | Y = D(S1 S0) |
| `DEMUX2` | D, S | Y0, Y1 (Y(S) = D, the other is 0) |
| `DEMUX4` | D, S1, S0 | Y0..Y3 (Y(S1 S0) = D, the others are 0) |
| `DECODER2` | A1, A0 | Y0..Y3 (one-hot: Y(A1 A0) = 1) |
| `DECODER3` | A2, A1, A0 | Y0..Y7 (one-hot) |
| `ENCODER4` | D0..D3 | A1, A0 |
| `ENCODER8` | D0..D7 | A2, A1, A0 |

Encoders are plain (non-priority): output bit b is the OR of every input whose index has bit b set, which is the
binary index of the active input when exactly one input is 1. For several active inputs the outputs are the OR of
their indices, exactly like the standard gate-level encoder. Analysis expands each block into AND/OR/NOT
expressions, so truth tables, K-maps and equivalence checks work unchanged.

## Constants and 74xx ICs

| Type | Input pins (`input_index` 0..) | Output pins (`output_index` 0..) |
|---|---|---|
| `VCC` | none (`inputs: 0`) | constant 1 |
| `GND` | none (`inputs: 0`) | constant 0 |
| `74138` | A, B, C, G1, /G2A, /G2B | /Y0../Y7, active low. Enabled when G1 = 1, /G2A = 0 and /G2B = 0; C is the MSB of the address. |
| `74153` | A, B, /1G, 1C0..1C3, /2G, 2C0..2C3 | 1Y, 2Y. A (LSB) and B (MSB) select for both halves; each half outputs 0 while its strobe /nG is 1. |

A leading `/` marks an active-low pin. Tie unused enables and data pins with `VCC` or `GND`.

## Flip-flop ICs and sequential exercises

| Type | Input pins (`input_index` 0..) | Output pins (`output_index` 0..) |
|---|---|---|
| `7476` | 1CLK, /1PRE, /1CLR, 1J, 1K, 2CLK, /2PRE, /2CLR, 2J, 2K | 1Q, /1Q, 2Q, /2Q. Dual JK, triggers on the **falling** clock edge. |
| `7474` | 1D, 1CLK, /1PRE, /1CLR, 2D, 2CLK, /2PRE, /2CLR | 1Q, /1Q, 2Q, /2Q. Dual D, triggers on the **rising** clock edge. |

- `/PRE` and `/CLR` are active low and asynchronous; `/CLR` wins if both are low. Tie unused pins to `VCC`:
  unlike real TTL, the analysis requires every pin to be wired (an unwired pin is a `MISSING_INPUT` error).
- A flip-flop's output does not depend on its inputs within the same instant, so a flip-flop breaks a feedback loop.
  Counters and shift registers are therefore not reported as `CYCLE_DETECTED`; real combinational loops still are.
- Every flip-flop starts at 0 and, in the live editor, the **Reset flip-flops** button returns them to 0.

A task checks a sequential circuit with `sequence` (instead of `expected_expression` and friends):

```json
{
  "id": "async_up_counter_2bit",
  "inputs": ["CLK"], "outputs": ["Q1", "Q0"],
  "sequence": {
    "clock": "CLK",
    "steps": [
      { "outputs": { "Q1": 0, "Q0": 1 } },
      { "inputs": { "M": 0 }, "outputs": { "Q1": 1, "Q0": 0 } }
    ]
  }
}
```

Each step sets the listed `inputs` (others keep their value; all start at 0), gives one full pulse
(0, then 1, then 0) on the `clock` input, then compares the listed `outputs`. `clock` is optional: without it
(a latch) each step just sets the inputs and lets the circuit settle. Flip-flops sample all their
pins simultaneously on the active edge, so a flip-flop clocked by another flip-flop's output (a ripple
counter) triggers one settling step later, like real hardware. The result is returned as
`deterministic.sequence` (rows of inputs, expected and actual outputs); no truth table or K-map is produced.

### Gate-level feedback (latches)

In an exercise with a `sequence`, gates may be wired in a feedback loop: two cross-coupled NAND gates form an
SR latch (`Q = NAND(S, Qn)`, `Qn = NAND(R, Q)`). Gates are evaluated in the order they appear in the circuit until
nothing changes; every input, flip-flop and gate output starts at 0, so write the first steps to set the state you
want to test (a latch's power-up state is not defined). A circuit that never settles (a ring oscillator) is reported
as `UNSTABLE_CIRCUIT`. In exercises that check a truth table, a loop is still a `CYCLE_DETECTED` error.
