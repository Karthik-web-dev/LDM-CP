# LDM Circuit Lab

Define the function you want (type an **equation** such as `A'B + AB'`, or fill in a **truth table** with don't-cares), or pick a built-in exercise. Then build a circuit in the browser, press **Validate**, and get:

1. **Exact circuit analysis.** The backend turns your wiring into a graph, checks its structure, derives the Boolean expression of every output, builds a full truth table, and checks logical equivalence with the exercise. No AI is involved in this step.
2. **AI tutor feedback.** An LLM receives the circuit and the exact analysis as established facts. It explains what is wrong and how to fix it. It cannot override the verdict.

```
React SVG editor ──normalized JSON──▶ FastAPI ──▶ structure ▶ graph ▶ topo sort ▶ Boolean AST ▶ truth table ▶ equivalence
                                         │                                                               │
                                         └──────────────── circuit + analysis ──▶ LLM tutor ◀────────────┘
```

## Requirements

- Python 3.12 (a venv already exists in `venv/`)
- Node.js 20+

## Run

Backend (from the repo root):

```bash
venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

```bash
cd backend && ../venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` to `http://127.0.0.1:8000`.

### AI tutor configuration

Copy `backend/.env.example` to `backend/.env` and set `AI_API_KEY`. An OpenRouter (`sk-or-...`), Anthropic (`sk-ant-...`) or OpenAI key works; the provider is detected from the prefix, and `AI_MODEL` picks the model. With no key the app still works: AI feedback is shown as unavailable and the exact analysis is unaffected. Set `AI_PROVIDER=mock` for canned offline feedback during development. See [AI_VALIDATION.md](AI_VALIDATION.md).

The key is read only by the backend. The browser never talks to the AI provider.

## Test

```bash
cd backend && ../venv/Scripts/python.exe -m pytest
```

```bash
cd frontend && npm test && npm run typecheck
```

Automated tests never call a real AI provider (they use `MockAIValidator` or a stubbed SDK client).

## Using the editor

- **Target**: choose *My own target* in the picker, then use the **Target** tab to type an equation or click through a truth table (cells cycle 0 → 1 → X). The backend previews how it understood your target (its truth table, or an equivalent simplified equation) before you use it.
- **+ Input / + Output / gate buttons** add components. Choosing an exercise pre-places its inputs and outputs.
- **Drag from a pin to another pin** to wire them. Wiring into an already-connected input replaces the old wire.
- **Click an input** to toggle it between 0 and 1. The live preview lights wires and output lamps.
- **Select** a part to rename it, change a gate's type or number of inputs, or delete it (the Delete key also works).
- **Hint** asks the AI tutor for a next-step nudge at any stage. **Validate** gives the full check plus tutor feedback.
- **Show K-map** displays the Karnaugh map of the target, or of your circuit, with the simplifier's groups highlighted. It's computed by the backend, with no AI involved.
- **Circuit JSON** tab shows exactly what is sent to the backend.
- Circuits autosave per exercise in the browser.

## Demo mode and the AI circuit builder

Every built-in exercise has a stored, verified circuit in `backend/app/data/golden/`.

- **Demo mode** (checkbox in the title bar): no AI is called anywhere. Type what you want in the **AI build** tab (for example `half adder` or `full adder using 74153`) and the matching stored circuit opens, switching to its exercise, and is checked offline in well under a second. The **Load demo** button opens the selected exercise's circuit. Use it when presenting.
- **Backtest**: proves every exercise still has a stored circuit that passes. Run it before a demo:

```bash
cd backend && ../venv/Scripts/python.exe -m app.tools.backtest
```

  It also runs as part of `pytest` (`tests/test_golden.py`), so deleting or breaking a stored circuit fails the tests. Regenerate the reference circuits with `python -m app.tools.build_golden`.
- **Build with AI** (AI build tab, demo mode off) has three modes: **Describe it** (plain words, no target: the AI states the target it built to), **Build for target** (from scratch for the selected target), and **Improve my circuit** (builds on what is on the workspace, keeping your parts and positions). In every mode the AI's circuit is verified by the exact checker and failures are fed back so it can retry (up to `GENERATE_ATTEMPTS`, default 3, within `GENERATE_TIMEOUT_SECONDS`, default 240). Modes 1 and 2 fall back to a stored circuit if the AI fails (labelled as a fallback); mode 3 never replaces your circuit. See `docs/HOW_TO_START.md` section 8.
- Use a fast model for live building (set `AI_MODEL` in `backend/.env`). Free models can be slow or get retired; the response says which model was not found.

## Documentation

- [HOW_TO_START.md](HOW_TO_START.md): step-by-step setup, API key, troubleshooting
- [ARCHITECTURE.md](ARCHITECTURE.md): modules, pipeline, design rules
- [CIRCUIT_FORMAT.md](CIRCUIT_FORMAT.md): the normalized circuit JSON
- [API.md](API.md): HTTP endpoints
- [AI_VALIDATION.md](AI_VALIDATION.md): the AI tutor layer, prompt, and failure handling
