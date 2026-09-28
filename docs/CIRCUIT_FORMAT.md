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
| `gates[].type` | `AND`, `OR`, `NOT`, `NAND`, `NOR`, `XOR`, `XNOR`, `BUFFER` (aliases: `INV`, `INVERTER` → NOT, `BUF` → BUFFER). Case-insensitive. |
| `gates[].inputs` | Number of input pins. Optional: defaults to the type's default (2, or 1 for NOT/BUFFER). AND/OR/NAND/NOR/XOR/XNOR accept 2 or more; NOT/BUFFER exactly 1. |
| `connections[].from` | Id of an input or gate (the driver). |
| `connections[].to` | Id of a gate or output (the sink). |
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
