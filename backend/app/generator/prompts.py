"""Prompts for the circuit generator. The model returns circuit JSON; it is never trusted.

Every answer is checked by the deterministic validator before the student sees it, and a failure is
fed back to the model together with the exact problems found.

Three ways to ask (``intent`` in the API):

* ``describe``: only a plain-language request. The model must also return a ``spec``, a precise
  statement of what the circuit does, and the circuit is checked against that spec.
* ``target``: build from scratch to a given target.
* ``extend``: improve the circuit the student already has so it meets the given target.
"""

import json
from typing import Any

from app.analysis.gates import GATE_DEFINITIONS
from app.models.task import Task


def _parts_catalogue() -> str:
    lines = []
    for d in GATE_DEFINITIONS.values():
        arity = d.arity_text()
        lines.append(f"- {d.type} ({arity} input pins): {d.description}")
    return "\n".join(lines)


EXAMPLE = {
    "version": 1,
    "inputs": [{"id": "input_1", "label": "A"}, {"id": "input_2", "label": "B"}],
    "gates": [{"id": "gate_1", "type": "XOR", "inputs": 2}, {"id": "gate_2", "type": "AND", "inputs": 2}],
    "outputs": [{"id": "output_1", "label": "S"}, {"id": "output_2", "label": "C"}],
    "connections": [
        {"from": "input_1", "to": "gate_1", "input_index": 0},
        {"from": "input_2", "to": "gate_1", "input_index": 1},
        {"from": "input_1", "to": "gate_2", "input_index": 0},
        {"from": "input_2", "to": "gate_2", "input_index": 1},
        {"from": "gate_1", "to": "output_1"},
        {"from": "gate_2", "to": "output_2"},
    ],
}

EXAMPLE_SPEC = {"inputs": ["A", "B"], "outputs": ["S", "C"], "expected_outputs": {"S": "A XOR B", "C": "A AND B"}}

# A memory example for requests like "SR latch": gate-level feedback, no clock, explicit set/hold/reset steps.
LATCH_EXAMPLE = {
    "spec": {
        "inputs": ["S", "R"], "outputs": ["Q", "Qn"],
        "sequence": {"steps": [
            {"inputs": {"S": 0, "R": 1}, "outputs": {"Q": 1, "Qn": 0}},
            {"inputs": {"S": 1, "R": 1}, "outputs": {"Q": 1, "Qn": 0}},
            {"inputs": {"S": 1, "R": 0}, "outputs": {"Q": 0, "Qn": 1}},
            {"inputs": {"S": 1, "R": 1}, "outputs": {"Q": 0, "Qn": 1}},
        ]},
    },
    "circuit": {
        "version": 1,
        "inputs": [{"id": "input_1", "label": "S"}, {"id": "input_2", "label": "R"}],
        "gates": [{"id": "gate_1", "type": "NAND", "inputs": 2}, {"id": "gate_2", "type": "NAND", "inputs": 2}],
        "outputs": [{"id": "output_1", "label": "Q"}, {"id": "output_2", "label": "Qn"}],
        "connections": [
            {"from": "input_1", "to": "gate_1", "input_index": 0}, {"from": "gate_2", "to": "gate_1", "input_index": 1},
            {"from": "input_2", "to": "gate_2", "input_index": 0}, {"from": "gate_1", "to": "gate_2", "input_index": 1},
            {"from": "gate_1", "to": "output_1"}, {"from": "gate_2", "to": "output_2"},
        ],
    },
    "explanation": "Two cross-coupled NAND gates form an active-low SR latch.",
}

SPEC_RULES = """If the request is not a digital logic circuit, or cannot be built from the available parts, do not invent one: reply only {"unsupported": "<short reason>"}.
When no target is given you must also return a "spec": a precise statement of what the circuit does, so it can be checked.
The reply is then {"spec": <spec>, "circuit": <circuit>, "explanation": "..."}.
A spec has "inputs" (list of input labels), "outputs" (list of output labels), and exactly ONE of:
- "expected_outputs": {"S": "A XOR B", "C": "A AND B"}: one equation per output, over the input labels, using AND OR NOT XOR NAND NOR XNOR and parentheses.
- "expected_truth_table": {"Y": [0, 1, 1, 0]}: one column per output with 2^n values in binary counting order (the first input is the most significant bit; "X" means don't care).
- "sequence": {"clock": "CLK", "steps": [{"inputs": {"M": 0}, "outputs": {"Q1": 0, "Q0": 1}}]}: for circuits with memory (flip-flops, latches, counters, registers). Each step sets the listed inputs, gives one full clock pulse, then checks the outputs. Leave "clock" out for a circuit with no clock (a latch): each step then just sets the inputs. Every input, flip-flop and gate output starts at 0, so set the state you want to test in the first steps (a latch's power-up state is not defined).
Labels are identifiers (letters, digits, underscore; not an operator name). The circuit's input and output labels must equal the spec's, and the circuit must really do what the spec says."""


def build_system_prompt(with_spec: bool = False) -> str:
    reply_format = (
        'a single JSON object {"spec": <spec>, "circuit": <circuit>, "explanation": "<one or two sentences>"}'
        if with_spec
        else 'a single JSON object {"circuit": <circuit>, "explanation": "<one or two sentences>"}'
    )
    spec_section = f"\n{SPEC_RULES}\n" if with_spec else ""
    latch_example = f"\n\nExample with memory (SR latch from NAND gates):\n{json.dumps(LATCH_EXAMPLE)}" if with_spec else ""
    return f"""You design digital logic circuits for a circuit editor and answer with JSON only.

Output format: {reply_format}. No markdown, no extra text.

A circuit has: "version" (always 1), "inputs", "gates", "outputs", "connections".
- inputs: [{{"id": "input_1", "label": "A"}}]. Use the exact input labels the task gives.
- gates: [{{"id": "gate_1", "type": "AND", "inputs": 2}}]. "inputs" is the number of input pins and must be valid for the type.
- outputs: [{{"id": "output_1", "label": "Y"}}]. Use the exact output labels the task gives.
- connections: [{{"from": <id of an input or gate>, "to": <id of a gate or output>, "input_index": <pin>, "output_index": <pin>}}].
  * input_index is the 0-based input pin of the target gate. Leave it out when the target is an output.
  * output_index is the 0-based output pin of the source. Leave it out (or 0) unless the source part has several outputs.
- Ids: input_1, input_2, ..., gate_1, gate_2, ..., output_1, output_2, ... and every id is unique.
- Every gate input pin and every output must have exactly one driver. A driver can feed any number of pins.
- No feedback loops through plain gates, EXCEPT to build memory: when the task is a "sequence" (or you write a "sequence" spec), gate-level feedback such as two cross-coupled NAND gates is how a latch is built. Flip-flops (7476, 7474) may always feed back, because they store a value.
- Do not include positions or any other fields.

Available parts (pin order matters; a leading / means active low):
{_parts_catalogue()}

Rules for ICs and constants:
- Tie every unused input of an IC (enables, presets /PRE, clears /CLR, spare data pins) to a VCC or GND part. All pins must be wired.
- VCC and GND have no input pins ("inputs": 0) and one output. One VCC and one GND part can drive many pins.
- For flip-flop circuits the clock is an ordinary input (label it CLK unless the task names it). Each step pulses the clock once. All flip-flops start at 0.
- The 7476 triggers on the falling clock edge, the 7474 on the rising edge.
{spec_section}
Example (half adder, S = A XOR B, C = A AND B):
{json.dumps({"spec": EXAMPLE_SPEC, "circuit": EXAMPLE, "explanation": "XOR gives the sum and AND the carry."} if with_spec else {"circuit": EXAMPLE, "explanation": "XOR gives the sum and AND the carry."})}{latch_example}

Keep the circuit small and correct. If you are told a previous attempt failed, fix exactly the listed problems."""


def _retry_block(previous: tuple[str, str] | None) -> list[str]:
    if not previous:
        return []
    circuit_json, problems = previous
    return [
        "Your previous attempt failed.",
        f"Previous reply: {circuit_json}",
        f"Problems found by the checker:\n{problems}",
        "Return a corrected reply.",
    ]


def build_user_message(task: Task, target: dict[str, Any], user_prompt: str | None, previous: tuple[str, str] | None) -> str:
    """Mode "target": build from scratch to a given target."""
    parts = [
        f"Exercise: {task.title or task.id}",
        f"Description: {task.description}",
        f"Input labels: {', '.join(task.inputs) or '(choose sensible labels)'}",
        f"Output labels: {', '.join(task.output_labels())}",
        "Target (must be matched exactly):",
        json.dumps(target, separators=(",", ":")),
    ]
    if task.hint:
        parts.append(f"Hint: {task.hint}")
    if user_prompt:
        parts.append(f"Extra instructions from the student: {user_prompt.strip()[:1000]}")
    return "\n".join(parts + _retry_block(previous))


def build_describe_message(user_prompt: str, previous: tuple[str, str] | None) -> str:
    """Mode "describe": only a plain-language request; the model decides the exact behaviour."""
    parts = [
        "No target is given. Work out exactly what the student wants from this request, state it as a spec, and build the circuit.",
        f"Student request: {user_prompt.strip()[:1000]}",
        "Use short input and output labels (for example A, B, Cin, S, Cout). Prefer basic gates unless the student names an IC.",
    ]
    return "\n".join(parts + _retry_block(previous))


def build_extend_message(
    task: Task, target: dict[str, Any], current: dict[str, Any], current_status: str, user_prompt: str | None,
    previous: tuple[str, str] | None,
) -> str:
    """Mode "extend": improve the student's existing circuit so it meets the target."""
    parts = [
        f"Exercise: {task.title or task.id}",
        f"Description: {task.description}",
        "Target (the finished circuit must match it exactly):",
        json.dumps(target, separators=(",", ":")),
        "The student already built this circuit. Build on it: keep its ids, labels and parts wherever they are correct, "
        "and add, remove or rewire only what is needed. Return the COMPLETE updated circuit, not just the changes.",
        f"Current circuit: {json.dumps(current, separators=(',', ':'))}",
        f"What the checker says about the current circuit:\n{current_status}",
    ]
    if task.hint:
        parts.append(f"Hint: {task.hint}")
    if user_prompt:
        parts.append(f"What the student wants changed: {user_prompt.strip()[:1000]}")
    return "\n".join(parts + _retry_block(previous))
