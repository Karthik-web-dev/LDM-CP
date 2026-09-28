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

## Documentation

- [HOW_TO_START.md](HOW_TO_START.md): step-by-step setup, API key, troubleshooting
- [ARCHITECTURE.md](ARCHITECTURE.md): modules, pipeline, design rules
- [CIRCUIT_FORMAT.md](CIRCUIT_FORMAT.md): the normalized circuit JSON
- [API.md](API.md): HTTP endpoints
- [AI_VALIDATION.md](AI_VALIDATION.md): the AI tutor layer, prompt, and failure handling
