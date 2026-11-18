# LDM Circuit Lab: team pitch

**One line:** a logic-design workbench where an *exact* checker decides whether a circuit is right, and AI helps build and explain circuits but is never trusted.

**Why it matters:** the lab needs real parts (gates, MUX, decoders, 74xx ICs, flip-flops, counters). Students need to know *why* a circuit is wrong, and a chatbot alone cannot prove anything.

**Team split (about 2 to 3 minutes each):** Frontend, then Backend, then AI Integration, then Testing. The shared demo script is at the end.

---

## 1. Frontend: the workbench

**Opening line:** "This is what you see and touch: a drag-and-drop editor in the style of Electronics Workbench, with every part simulated live in the browser."

### What we built
- **React + TypeScript + Vite**, with the circuit drawn in **SVG**. No drawing library.
- **Parts bin (left):** Switch, Lamp, VCC, GND, **Clock**; the gates AND, OR, NOT, NAND, NOR, XOR, XNOR, BUF; the blocks MUX 2:1/4:1, DEMUX 1:2/1:4, decoder 2:4/3:8, encoder 4:2/8:3; and a dropdown of **74xx ICs**: 74138, 74153, 7476, 7474. Drag a part onto the workspace, or click to add it.
- **Wiring:** drag from a pin to a pin. Blocks have several output pins; each pin is named (D0, S1, /Y3, ...).
- **Live simulation:** click an input to flip it and watch wires and lamps (red = 1). Flip-flops hold their state between clicks.
- **Clock part:** a square-wave source with a frequency (0.5 to 10 Hz), its own Run/Stop, and a toolbar **Run clocks** button. A 2-bit counter at 1 Hz counts once a second. The **Pulse** button gives one clock pulse; **Reset flip-flops** returns everything to 0. A **power switch** (I/O) stops the simulation.
- **Latches in the browser:** two cross-coupled NAND gates keep their value because loop gates remember their last output.
- **Analysis views:** Boolean expression per output, full truth table (yours vs expected), **Karnaugh map** with grouped terms, and a pulse-by-pulse table for counters.
- **AI build tab:** three modes (see section 3) and a **Demo mode** switch in the title bar.
- **Autosave** per exercise in the browser, so a refresh loses nothing.

### How it is built (talking points)
- **State lives in one reducer** (`editorReducer`). Components, wires, switch positions and stored flip-flop bits are plain data, so it is easy to test.
- **The live simulator is only for feedback.** Correctness, expressions and truth tables always come from the backend. The frontend never decides if a circuit is right.
- **Circuit JSON is the only contract.** `circuitSerializer` turns the editor state into a normalized JSON; the editor's own details (positions, clock frequency) never reach the checker.
- **Electronics Workbench look** is done with CSS tokens: grey window chrome, navy title bar, white workspace, red for "signal is 1".

### Key files
`frontend/src/pages/CircuitPage.tsx`, `circuit/editorReducer.ts`, `circuit/simulator.ts`, `circuit/gateLibrary.ts`, `components/CircuitEditor`, `components/PartsBin`, `components/AiBuild`.

### Likely question and answer
- **Q: How does a loop like an SR latch simulate without hanging?** The simulator evaluates gates in order for a bounded number of passes, and gates on a feedback loop start from a stored value, so a latch holds and an oscillator stops instead of freezing the page.

---

## 2. Backend: the exact checker

**Opening line:** "Everything that decides right or wrong is here, and it contains no AI."

### The pipeline (FastAPI + Pydantic, Python 3.12)
1. **Structure:** unknown gates, wrong pin counts, undriven pins and outputs, two drivers on one pin, dangling gates, bad labels, cycles. Problems on gates that feed nothing are warnings, not errors.
2. **Graph** with per-pin edges, then **topological sort** (deterministic, with a concrete cycle reported).
3. **Boolean AST** per output, built in dependency order so shared sub-circuits share nodes.
4. **Truth table** over every input combination.
5. **Equivalence** against the target: column by column, never by comparing text. Don't-care rows always match. Failures come with **counterexample rows**.
6. **K-map** from the truth table using Quine-McCluskey simplification.

### Targets
An exercise's target can be an **equation** (`A'B + AB'`), a **truth table** with don't-cares, or a **sequence** for circuits with memory.

### Circuits with memory
- **Flip-flop ICs:** 7476 (dual JK, falling edge) and 7474 (dual D, rising edge), with active-low preset and clear.
- **One simulator** (`analysis/sequential.py`) handles flip-flops *and* gate-level feedback. Inputs are set, a clock pulse is given if the exercise has one, outputs are compared with the expected step.
- **Loops are legal only where memory is the point.** In a truth-table exercise a loop is still an error. A circuit that never settles is reported as `UNSTABLE_CIRCUIT`.

### Data and endpoints
- **20 exercises** (`data/tasks.json`) covering all seven assignments, with a stored, verified circuit for each (`data/golden`).
- **Endpoints:** `/validate`, `/kmap`, `/tasks`, `/generate`, `/demo/match`, `/demo/catalog`, `/golden/{id}`. Route handlers are thin; the logic lives in services.
- **Limits** on circuit size and truth-table size, and a request-size limit.

### Design rules we kept
The model never computes Boolean expressions. Equivalence is never a string comparison. Malformed circuits are reported, never silently fixed (Pydantic `extra="forbid"`).

### Key files
`backend/app/analysis/` (`gates.py`, `graph.py`, `structural_validator.py`, `expression_generator.py`, `equivalence.py`, `sequential.py`), `services/validation_service.py`, `api/routes/validation.py`.

### Likely question and answer
- **Q: Why is an ordinary loop an error but a latch allowed?** In a combinational exercise there is nothing to remember, so a loop is a mistake. In an exercise that describes behaviour over steps, feedback is exactly how a latch stores a bit.

---

## 3. AI Integration: useful AI that is never trusted

**Opening line:** "The AI can build circuits. But before you see any of them, the exact checker has to agree."

### Three build modes (AI build tab)
| Mode | You give | What happens |
|---|---|---|
| **Describe it** | Plain words, no target | The AI writes down a precise **spec** of what it builds (equations, a truth table or a step sequence). The circuit is checked against that spec, and the spec becomes your target. |
| **Build for target** | An exercise or custom target | The AI builds from scratch to match it. You can add instructions like "use only NAND gates". |
| **Improve my circuit** | Your partly built circuit and a target | The AI sees your circuit and what the checker says is wrong, keeps your parts and **their positions**, and fixes the rest. |

### How every answer is handled
1. **Ask** (the model returns JSON only).
2. **Verify** with the same analysis that grades students.
3. **Retry** with the exact problems if it fails (up to 3 attempts).
4. **Auto-place** the circuit on the canvas.
5. **Fall back safely:** Build for target shows the stored circuit labelled as a fallback; Describe shows a stored circuit only if the words really *name* it; Improve **never** replaces your work.

### What makes it dependable
- **Can decline:** a request that is not a logic circuit ("a circuit that makes me a sandwich") is refused, not invented.
- **Transient provider errors are retried;** real configuration errors (bad key) fail immediately and say why.
- **Reasoning models** get a 16,000-token budget and a 240-second limit, because they spend most tokens thinking.
- **Provider-agnostic:** Anthropic, OpenAI-compatible gateways (including OpenRouter), a mock for tests, or disabled. The API key stays on the server.
- **AI tutor** (separate from building): gets the circuit and the exact results as facts and can only explain; it cannot change the verdict.

### Demo mode (no AI at all)
Type "half adder" and the stored circuit opens in under a second. The words are matched by plain text rules, so the same words always give the same circuit. The matcher is **strict after an AI failure**: "use only NAND gates" or "use a 7476" never switch the exercise.

### Honest limit
Describe mode checks the circuit against the AI's *own* reading of the request. That catches wiring mistakes but not a misunderstanding, so the target the AI built to is always shown for you to confirm.

### Key files
`backend/app/services/generation_service.py`, `generator/prompts.py`, `ai/client.py`, `services/demo_matcher.py`, `generator/layout.py`.

### Likely question and answer
- **Q: What stops the AI from cheating?** It never produces the verdict. A wrong circuit fails the checker and is not shown; the model is only told the exact failing rows so it can try again.

---

## 4. Testing: how we know it works

**Opening line:** "We tested it at every level, including against the real AI, and some of the bugs we found are the reason it is trustworthy now."

### Numbers (latest run)
| What | Result |
|---|---|
| Backend tests (pytest) | **356 pass** |
| Frontend tests (vitest) | **53 pass**, TypeScript strict, production build succeeds |
| Backtest: stored circuit vs its exercise | **20 of 20 pass** |
| Fuzz: stored circuits randomly broken | 250 mutations per exercise in the suite; a heavy run of about **30,000** broken circuits caused **0 crashes** |
| Live AI, first battery (all 3 modes) | **13 of 13** |
| HTTP end to end on the running server | **35 of 35** (generate, then validate, positions kept) |
| Harder live batch | 11 of 12; the miss was a provider hiccup, now retried |
| Real browser UI | All 3 AI modes driven through the page |

### What each kind of test protects
- **Unit tests:** gate logic, MUX/DEMUX/decoder/encoder truth tables, flip-flop and latch behaviour, K-map, matcher, layout.
- **Exercise backtest:** `python -m app.tools.backtest` runs every stored circuit through the real checker. Run it before any demo. It also runs inside the test suite.
- **Fuzzing:** random wire and gate deletions, type and pin changes, loops and duplicates. Proved useful: see below.
- **AI tests without a network:** a scripted fake AI covers correct answers, wrong answers that get retried, garbage replies, timeouts, declines and provider errors in all three modes.
- **Live tests:** the real model, through the real HTTP endpoint, then validating what came back.

### Bugs testing found (and we fixed)
1. **Wrong circuit shown:** "sr flip flop using nand gates" opened the NAND-gate exercise because of the words "nand gate". Fixed with strict matching, plus latch support so the correct answer can pass. A regression test uses the exact prompt.
2. **Crash:** a stray gate with an unwired pin crashed the check. Found by reading, then confirmed that the fuzz test catches it.
3. **AI timed out and was cut off:** the reasoning model spent all 6,000 tokens thinking and hit a 60-second limit. Budget and time raised.
4. **Nonsense passed:** a request for a sandwich produced an AND gate that "passed" its own invented spec. The AI may now decline.
5. **One hiccup killed a build:** provider errors are now retried.
6. **Custom target ignored what you typed:** naming a circuit with a custom target selected silently built the old target. Fixed, and the target is now shown.

### How to run it all
```
cd backend
..\venv\Scripts\python.exe -m pytest
..\venv\Scripts\python.exe -m app.tools.backtest
cd ..\frontend
npm test
npm run typecheck
```
The automated tests never call a real AI provider, so they are free and work offline.

### Likely question and answer
- **Q: Is it perfect?** No, and we say so. Describe mode trusts the AI's own reading of the request, and live speed depends on the model (about 10 to 60 seconds in our runs). That is why demo mode and the backtest exist.

---

## Shared demo script (5 minutes)

1. **Frontend:** open *Half adder*, press **Load demo**. Flip A and B and watch S and C. Show the truth table and K-map.
2. **Frontend:** open the 2-bit down counter, press **Run clocks**. Change the clock to 2 Hz.
3. **Backend:** delete two wires. The checker says "Circuit incomplete" and names the problem. Show the counterexample rows.
4. **AI:** choose **Improve my circuit**, type "fix the wiring". The circuit is repaired and graded Correct; positions are unchanged.
5. **AI:** choose **Describe it**, type "SR flip flop using NAND gates". Read the target it built to, then flip S and R to set, hold and reset.
6. **Safety net:** switch on **Demo mode**, type `full adder using mux`. The stored 74153 circuit opens instantly with no AI.
7. **Testing:** show the backtest (20 of 20) and the test counts.

**Closing line:** "Exact where it counts, AI where it helps, and a demo mode that cannot fail."
