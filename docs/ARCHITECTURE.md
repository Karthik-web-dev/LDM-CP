# Architecture

## Three layers

| Layer | Where | Responsible for | Never does |
|---|---|---|---|
| Editor | `frontend/src/circuit`, `components/CircuitEditor` | Drawing, editing, live preview, serializing to normalized JSON | Derive expressions, truth tables, or correctness |
| Deterministic engine | `backend/app/analysis` | Structure checks, graph, topological order, Boolean AST, truth tables, equivalence | Call the AI |
| AI tutor | `backend/app/ai` | Explain the analysis, point to mistakes, suggest fixes | Decide correctness |

The authoritative verdict is:

```
is_correct = structurally_valid and no errors and equivalent_to_expected
```

The AI's own `valid` claim is kept as `model_verdict` for transparency. It is flagged in `anomalies` when it disagrees.

## Backend modules

```
backend/app/
  main.py                      FastAPI app, CORS, body-size limit, 422 formatting
  config.py                    Settings + Limits (env vars / .env)
  api/routes/validation.py     POST /validate, POST /tasks/preview, GET /tasks, GET /gates (thin: no logic)
  api/dependencies.py          Wiring: service + task repository
  models/                      Pydantic: circuit, task, analysis results, AI, API envelopes
  analysis/
    gates.py                   Central gate registry: arity + Boolean semantics
    boolean_ast.py             Immutable AST (Variable, Const, Not, And, Or, Xor, Nand, Nor, Xnor) + renderer
    graph.py                   Circuit -> directed graph with per-pin edges; rejects invalid connections
    topological_sort.py        Kahn's algorithm, deterministic tie-break, concrete cycle extraction
    structural_validator.py    All structural checks -> machine-readable issues
    expression_generator.py    Graph + topo order -> AST per output
    evaluator.py               Evaluate an AST (memoized over shared sub-expressions)
    truth_table.py             2^n assignments -> table
    equivalence.py             Truth-table comparison, counterexamples, output mapping
    expression_parser.py       Parses target equations ("(A AND B) OR NOT C", "A & B | !C", "A'B + AB'")
    expected_function.py       The target, as an equation or a truth table (with don't-cares), evaluable per row
    minimize.py                Quine-McCluskey: truth table -> simplified sum-of-products (for display)
  ai/
    client.py                  AIValidator interface; Anthropic, Mock, Disabled implementations
    prompts.py                 System prompt + data-only user message
    validator.py               Strict response parsing + reconciliation with the exact verdict
  services/
    validation_service.py      The orchestration pipeline
    task_repository.py         Built-in exercises from data/tasks.json
```

## Pipeline (`ValidationService.validate`)

1. **Limits.** Reject oversized circuits (`LIMIT_EXCEEDED`).
2. **Graph.** Build the graph. Unknown endpoints, outputs used as drivers, inputs used as sinks, and out-of-range pins become `INVALID_CONNECTION`.
3. **Structure.** Checks for duplicate ids and labels, invalid labels, missing outputs, unknown gates, gate arity, undriven pins and outputs, multiple drivers, dangling gates, unconnected inputs, and cycles. Problems on gates that feed no output are warnings, not errors.
4. **Target.** Build the expected function from the task: parse the equation(s), or take the truth-table columns directly (don't-cares become `None`). Parse failures are `INVALID_TASK`.
5. If there are any errors, stop here and return them. The AI is not called, because these errors are already fully explained.
6. **AST.** Visit nodes in topological order, so every driver's expression exists before its sinks. Shared sub-circuits share AST nodes (a DAG).
7. **Render.** Render each output's expression. If the rendered text would exceed the limit (a DAG can render exponentially large), it is omitted with a warning. Correctness is still checked.
8. **Truth tables.** Build them over the union of circuit and task variables, for the circuit and for the expected function.
9. **Equivalence.** Compare output columns. Don't-care rows of a truth-table target always match. Single-output tasks match the single circuit output regardless of label; multi-output tasks match by label. The result includes mismatch counts and counterexample rows.
10. **AI** (optional). Build the payload, check its size, call the provider, validate the response, and reconcile it with the exact verdict.

## Design rules (from the spec)

1. The LLM never computes Boolean expressions.
2. Equivalence is never decided by string comparison.
3. AI output cannot override deterministic correctness.
4. The analysis engine knows nothing about the editor, only the normalized JSON.
5. No business logic in route handlers.
6. AI credentials exist only in the backend environment.
7. Tests never call a real AI provider.
8. Malformed circuits are reported, never silently fixed. (The Pydantic models use `extra="forbid"`.)
9. Every component has a stable id. The editor never reuses one.
10. Every algorithm has unit tests (`backend/tests`, `frontend/src/circuit/circuit.test.ts`).

## Adding a gate

1. Add a `GateDefinition` to `backend/app/analysis/gates.py`.
2. If it needs a new operator, subclass `NaryOp` in `boolean_ast.py` (with `symbol` and `combine`), and add the keyword to `expression_parser.py` if tasks should be able to use it.
3. Add it to `GATES` / `GATE_ORDER` in `frontend/src/circuit/gateLibrary.ts` and give it a shape in `CircuitEditor.tsx`.
4. Add tests.

The graph engine, validator, generator, evaluator, and UI panels need no changes.

## Frontend

```
frontend/src/
  circuit/circuitTypes.ts      Editor model + normalized JSON types
  circuit/editorReducer.ts     All editing operations (pure reducer)
  circuit/circuitSerializer.ts Editor state <-> normalized JSON (the adapter)
  circuit/gateLibrary.ts       Gate arity, pin geometry, preview semantics
  circuit/simulator.ts         Live preview only (lamps and wire colours)
  api/validationApi.ts         Typed API client
  pages/CircuitPage.tsx        Page state, two-stage validation, autosave
  components/                  CircuitEditor, Toolbar/Inspector, TaskPanel, ValidationPanel, TruthTable, ...
```

Validation runs in two requests so results appear quickly. First `include_ai=false` returns the exact analysis ("Analyzing circuit…"). Then, only if the circuit is structurally valid, `include_ai=true` fetches tutor feedback ("Generating feedback…"). The editor stays usable throughout, and results are marked stale if the circuit changes.
