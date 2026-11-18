# API (v1)

Base URL during development: `http://127.0.0.1:8000`. Interactive docs are at `/docs`.

## `POST /api/v1/validate`

Request (reference a built-in exercise by id, **or** send a full `task`):

```json
{
  "task_id": "and_gate_001",
  "circuit": { "version": 1, "inputs": [...], "gates": [...], "outputs": [...], "connections": [...] },
  "include_ai": true,
  "ai_mode": "feedback"
}
```

`ai_mode` is `"feedback"` (the default) or `"hint"`. Feedback explains the verdict and is skipped while the circuit has structural errors. A hint is a nudge towards the next step without the full solution, and works at any stage, including an empty canvas.

```json
{
  "task": {
    "id": "custom_1",
    "title": "Build an AND circuit",
    "description": "Y is 1 only when A and B are both 1.",
    "expected_expression": "A AND B",
    "inputs": ["A", "B"],
    "outputs": ["Y"]
  },
  "circuit": { ... }
}
```

Multi-output tasks use `"expected_outputs": {"S": "A XOR B", "C": "A AND B"}` instead of `expected_expression`.

A target can also be a truth table. Each output is a column over `inputs` in binary counting order (the first input is the most significant bit). `"X"` (also `"x"`, `"-"`, `null`) marks a don't-care row, which matches any circuit output:

```json
{
  "task": {
    "id": "custom",
    "inputs": ["A", "B", "C"],
    "outputs": ["Y"],
    "expected_truth_table": { "Y": [0, 0, 0, 1, 0, "X", 1, 1] }
  },
  "circuit": { ... }
}
```

Exactly one of `expected_expression`, `expected_outputs`, or `expected_truth_table` must be given. Truth-table targets need `inputs` (at most 10). All names must be identifiers. For truth-table targets, `comparisons[].expected_defined_by` is `"truth_table"` and `expected_expression` is an equivalent simplified equation.

Expected expressions accept `AND OR NOT XOR NAND NOR XNOR` (any case), the symbols `& && * · | || + ^ ! ~ ¬`, postfix `'` (NOT), constants `0 1`, and parentheses. Adjacent terms are ANDed (`A'B + AB'`, `A(B + C)`). A word made only of capital letters is split into single-letter variables (`A'BC` = `A' AND B AND C`). Names containing lowercase letters, digits or `_` stay whole (`Cin`, `S1`), and so do names listed in the task's `inputs`. Precedence from highest to lowest: NOT, AND/NAND, XOR/XNOR, OR/NOR.

Response `200`:

```json
{
  "success": true,
  "is_correct": false,
  "task": { "...": "resolved task" },
  "deterministic": {
    "structurally_valid": true,
    "expression": "(A OR B)",
    "output_expressions": { "Y": "(A OR B)" },
    "variables": ["A", "B"],
    "truth_table":          { "variables": ["A","B"], "outputs": ["Y"], "rows": [{ "inputs": [0,0], "outputs": [0] }, "..."] },
    "expected_truth_table": { "variables": ["A","B"], "outputs": ["Y"], "rows": ["..."] },
    "equivalent_to_expected": false,
    "comparisons": [{
      "expected_output": "Y", "circuit_output": "Y",
      "expected_expression": "A AND B", "circuit_expression": "(A OR B)",
      "equivalent": false, "mismatch_count": 2,
      "counterexamples": [{ "inputs": {"A":0,"B":1}, "expected": 0, "actual": 1 }]
    }],
    "evaluation_order": ["input_1", "input_2", "gate_1", "output_1"],
    "errors": [],
    "warnings": []
  },
  "ai": {
    "available": true,
    "summary": "Your circuit uses an OR gate, so ...",
    "issues": [{ "component_id": "gate_1", "type": "WRONG_GATE", "explanation": "..." }],
    "suggestions": ["Replace gate_1 with an AND gate."],
    "concept": "An AND gate outputs 1 only when all of its inputs are 1.",
    "model_verdict": false,
    "agrees_with_analysis": true,
    "anomalies": [],
    "model": "claude-opus-5",
    "skipped_reason": null, "error": null, "error_kind": null
  }
}
```

- `is_correct` is the authoritative verdict (structure is valid, there are no errors, and every expected output is equivalent).
- `ai` is always present. When no tutor feedback is available, `available` is `false` and either `skipped_reason` (not called: structural errors, `include_ai=false`) or `error` + `error_kind` (`disabled`, `timeout`, `rate_limited`, `auth`, `bad_request`, `unavailable`, `malformed_response`, `refused`, `truncated`, `prompt_too_large`, `unknown`) explains why. The deterministic result is unaffected either way.

Errors:

| Status | When |
|---|---|
| `404` | Unknown `task_id` |
| `413` | Body larger than 1 MB |
| `422` | Schema violation (missing or unknown fields, both or neither of `task`/`task_id`, ...). Body: `{"success": false, "detail": [{"loc", "msg", "type"}]}` |

## `POST /api/v1/tasks/preview`

Body: a task (as above). The response describes the target both ways, so the user can confirm it before building:

```json
{
  "valid": true,
  "errors": [],
  "inputs": ["A", "B", "C"],
  "outputs": ["Y"],
  "expressions": { "Y": "(B AND (A OR C))" },
  "simplified": { "Y": "((B AND C) OR (A AND B))" },
  "truth_table": { "variables": ["A","B","C"], "outputs": ["Y"], "rows": ["..."] }
}
```

`expressions` is the parsed equation (fully parenthesised). For truth-table targets it is a simplified equation derived from the table. An unparseable equation returns `valid: false` with messages in `errors`.

## `POST /api/v1/kmap`

Computes Karnaugh maps without using the AI, for functions of 1 to 4 inputs. The body is either `{"task_id": ...}` or `{"task": {...}}`, plus `"source": "target"` (the function to build) or `"source": "circuit"` (what the circuit computes; this also needs `"circuit"`). There is one map per output:

```json
{ "source": "target", "errors": [], "kmaps": [{
  "output": "Y", "variables": ["A","B","C"], "row_variables": ["A"], "col_variables": ["B","C"],
  "row_labels": ["0","1"], "col_labels": ["00","01","11","10"],
  "cells": [[{"row":0,"col":0,"minterm":0,"value":0}, "..."]],
  "groups": [{"term": "BC", "expression": "(B AND C)", "minterms": [3,7], "cells": [[0,2],[1,2]]}, "..."],
  "minimal_sop": "BC + AC + AB", "minterms": [3,5,6,7], "dont_cares": []
}]}
```

Rows and columns follow Gray-code order. `value` is `null` for don't-cares. `groups` are the implicants chosen by the Quine-McCluskey simplifier, so they always agree with `minimal_sop`.

## `POST /api/v1/generate`

Builds a circuit with the AI (or opens a stored one). Every AI circuit is checked by the exact analysis before it is returned; if the check fails, the AI is told the exact problems and retries (up to `GENERATE_ATTEMPTS`, within `GENERATE_TIMEOUT_SECONDS`).

```json
{
  "intent": "target",
  "task_id": "half_adder",
  "prompt": "use only NAND gates",
  "mode": "live",
  "circuit": { "version": 1, "...": "only for intent extend" }
}
```

| `intent` | Needs | What happens | If the AI cannot do it |
|---|---|---|---|
| `describe` | `prompt` (no target) | The AI states a precise `spec` of what it builds (equations, a truth table, or a step sequence) and the circuit is checked against that spec. The `spec` is returned so it can be adopted as the target. | A stored circuit is shown only if the prompt strictly names it (`source: "fallback"`), otherwise nothing. |
| `target` (default) | `task_id` or `task` | Builds from scratch for the target. | The stored circuit for that exercise (`source: "fallback"`), if there is one. |
| `extend` | `task_id` or `task`, and `circuit` | Improves the given circuit so it meets the target. Existing parts keep their positions; new ones are placed to the right. | Nothing is returned and the circuit is untouched. |

`mode: "demo"` never calls the AI: `target` returns the stored circuit, `describe` matches the prompt to a stored circuit by text.

```json
{
  "success": true,
  "source": "ai",
  "circuit": { "version": 1, "inputs": [], "gates": [], "outputs": [], "connections": [] },
  "explanation": "XOR gives the sum and AND the carry.",
  "attempts": 1,
  "notice": null,
  "model": "...",
  "spec": null,
  "matched_task_id": null
}
```

`source` is `ai` (verified AI circuit), `stored` (demo mode), `fallback` (the AI failed, a stored circuit is shown) or `none`. `spec` is set for `describe`. `matched_task_id` is set when a stored circuit is shown, so the client can switch to that exercise. Errors: `422` (no prompt for `describe`, no target for `target`/`extend`, no circuit for `extend`), `404` (unknown `task_id`).

## `POST /api/v1/demo/match`

`{ "prompt": "half adder", "strict": false }` returns `{ "best": {...} | null, "matches": [...] }`: the stored circuit a request names, by deterministic text matching (no AI). `best` is set only when a whole stored phrase matched. With `strict: true` only distinctive circuit names count, so instructions such as "use only NAND gates" match nothing.

## `GET /api/v1/demo/catalog`

Every stored circuit with `task_id`, `title`, `style` (`gates` or `ic`) and the part types it uses.

## `GET /api/v1/golden/{task_id}`

The stored, verified circuit for an exercise (`task_id`, `title`, `source`, `circuit`). `404` if there is none.

## Tasks with memory

A task can define `sequence` instead of `expected_expression` / `expected_outputs` / `expected_truth_table`, for counters, shift registers and latches. `POST /validate` then returns `deterministic.sequence` (one row per step with the inputs, expected and actual outputs) instead of a truth table. See [CIRCUIT_FORMAT.md](CIRCUIT_FORMAT.md).

## `GET /api/v1/tasks`

Lists built-in exercises (`backend/app/data/tasks.json`).

## `GET /api/v1/gates`

Lists supported gate types with their arity rules.

## `GET /health`

`{"status": "ok", "ai_provider": "anthropic" | "mock" | "disabled"}`
