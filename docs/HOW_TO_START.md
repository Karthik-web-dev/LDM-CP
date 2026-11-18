# How to start the project

This guide takes you from a fresh checkout to a running app on Windows. Commands are for **PowerShell**, run from the project root (`LDM CP`) unless stated otherwise.

The app has two parts, and both must be running:

| Part | Tech | Address |
|---|---|---|
| Backend (analysis + AI tutor) | Python / FastAPI | http://127.0.0.1:8000 |
| Frontend (circuit editor) | React / Vite | http://localhost:5173 |

---

## 1. Prerequisites

- **Python 3.12.** A virtual environment already exists in `venv\`. Check it with:
  ```powershell
  .\venv\Scripts\python.exe --version
  ```
- **Node.js 20+** (includes npm):
  ```powershell
  node --version
  ```
- **Optional: an API key** for the AI tutor. Any of these works:
  - an **OpenRouter** key (`sk-or-...`), from https://openrouter.ai/keys (gives access to many models: Claude, GPT, Gemini, ...)
  - an **Anthropic** key (`sk-ant-...`), from https://console.anthropic.com
  - an **OpenAI** key (`sk-...`), from https://platform.openai.com

  Without a key, everything except AI feedback still works.

---

## 2. Install dependencies (first time only)

Backend:

```powershell
.\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Frontend:

```powershell
cd frontend
npm install
cd ..
```

---

## 3. Configure the AI tutor

The AI tutor is called from the backend. Your key stays on the server and is never sent to the browser.

1. Create the config file from the template:
   ```powershell
   Copy-Item backend\.env.example backend\.env
   ```
2. Open `backend\.env` and paste your key. The provider is detected from the key's prefix.

   **OpenRouter:**
   ```ini
   AI_API_KEY=sk-or-v1-...your key...
   AI_MODEL=anthropic/claude-opus-5
   ```
   `AI_MODEL` is optional; `anthropic/claude-opus-5` is the default. You can use any model ID listed at https://openrouter.ai/models (for example `google/gemini-3.5-flash` or `openai/gpt-5.5`). Models that support *structured outputs* give the most reliable results. For others, the app falls back to asking for plain JSON automatically. Your OpenRouter account needs credits.

   **Anthropic:** `AI_API_KEY=sk-ant-...` (model defaults to `claude-opus-5`).
   **OpenAI:** `AI_API_KEY=sk-...` plus `AI_MODEL=` a model ID (required).

   The other defaults are fine. The ones you're most likely to change:

   | Setting | Default | Meaning |
   |---|---|---|
   | `AI_MODEL` | per provider (see above) | Which model to use |
   | `AI_ON_CORRECT` | `true` | Set `false` to skip AI calls when the circuit is already correct (saves cost) |
   | `AI_EFFORT` | `medium` | Anthropic only: `low` is faster and cheaper; `high` is more thorough |

**No key yet?** Choose one of these:
- Leave `AI_API_KEY` empty. AI feedback shows as "not configured"; the analysis works normally.
- Set `AI_PROVIDER=mock` to get canned offline feedback, which is useful for UI work.

> `backend\.env` holds a secret. It is listed in `.gitignore`. Never commit it or put the key in frontend code.

---

## 4. Start the backend

Open a terminal:

```powershell
cd backend
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The startup log shows which AI provider is active:

```
INFO ldm ai_provider=openrouter model=anthropic/claude-opus-5
```

(`disabled` means no key was found; `mock` means mock mode.)

To check it, open http://127.0.0.1:8000/health. The interactive API docs are at http://127.0.0.1:8000/docs.

Leave this terminal running.

---

## 5. Start the frontend

Open a **second** terminal:

```powershell
cd frontend
npm run dev
```

Then open **http://localhost:5173** in your browser.

The dev server forwards `/api/...` requests to the backend on port 8000, so no extra setup is needed.

---

## 6. Try it

1. Choose what to validate against:
   - **Your own target**: pick *✎ My own target* in the dropdown. In the **Target** tab, either type an equation (for example `A'BC + AB'C` or `(A AND B) OR C`; capital letters written together are separate inputs, while names like `Cin` stay whole) or switch to **Truth table**, enter the input names, and click output cells to cycle 0 → 1 → X (X = don't care). Check the preview, then press **Use this target**.
   - **An exercise**: pick one from the dropdown, for example *Build an AND circuit*.

   Either way, the target's inputs and outputs are placed on the canvas for you.
2. Click **AND** in the toolbar to add a gate.
3. Drag from input **A**'s pin to the gate's first input, then from **B** to the second input, then from the gate's output to **Y**.
4. Click the inputs to toggle them and watch the lamp.
5. Press **Validate**. The exact *Circuit Analysis* appears first, then the *AI Tutor Feedback*.

---

## 7. Load a circuit in demo mode (for presentations)

Every built-in exercise has a stored, verified circuit. Demo mode loads it in under a second and never calls the AI, so it cannot be affected by the network or by an API key problem.

**Before you present, run the backtest** (it proves every stored circuit still passes its exercise):

```powershell
cd backend
..\venv\Scripts\python.exe -m app.tools.backtest
```

You should see `PASS` on every line and `18/18 exercises pass` (the number grows if you add exercises). Any `FAIL` names the exercise to fix.

**To open a circuit by asking for it:**

1. Tick **Demo mode** in the blue title bar (top right). While it is on, the AI is never called: **Hint** is disabled and **Validate** shows only the exact analysis.
2. Open the **AI build** tab.
3. Type what you want in **What should I open?** and press **Enter** (or click **Open stored circuit**). For example:
   - `half adder`
   - `full adder`
   - `full adder using mux` (the stored version uses 74153 ICs)
   - `2 bit comparator using decoder`
   - `ripple counter`
   - `4 bit shift register`
   - `sr flip flop` or `sr latch`
   - `excess-3 to BCD` (direction matters: `BCD to excess-3` opens the other converter)
4. The app finds the stored circuit that matches your words, **switches to that exercise by itself** (you do not have to pick it first), puts the circuit on the workspace and checks it. You see a yellow tag such as **Stored reference circuit for "Half adder"**, **Correct** in the Validation tab, and the Boolean expressions and truth table.

Matching is plain text matching, not AI: the same words always open the same circuit, and it works without internet. Capitals, punctuation and filler words do not matter (`Build me a half-adder please` works). Each stored circuit is built either from basic gates or using an IC; the list in the tab marks every one with **gates** or **IC**.

If nothing matches, the tab says so and suggests close names. You can always click a name in the **Stored circuits** list in the same tab to open it directly.

**Other ways to load one:** pick the exercise in the dropdown and press **Load demo** in the toolbar.

**Counters and registers (the Clock part):** the clock input of a counter or shift register is a **Clock** part, drawn with a square-wave symbol and its frequency (for example `1 Hz`).
- **Run clocks** (toolbar) starts every clock; the button becomes **Stop clocks**. The counter then counts by itself, one step per clock period (a 2-bit counter at 1 Hz changes once a second). The clock shows `▶ running` while it runs.
- **Change the speed:** click the Clock part, choose a frequency (0.5, 1, 2, 5 or 10 Hz) in the bar above the workspace, and use **Run clock** / **Stop clock** to run just that one.
- **Step by hand:** with the clock stopped, click it to flip it, or press **Pulse** for one full clock pulse (one count).
- **Reset flip-flops** (toolbar) returns every flip-flop to 0.
- **Add your own:** drag **Clock** from *Sources & Indicators* in the parts bin. Several clocks are fine, each with its own frequency. Any ordinary switch can also be clocked at 1 Hz with **Auto clock**.
- The 7476 counts on the **falling** edge of the clock and the 7474 on the **rising** edge, so the count changes at that point of each period.

The tag disappears as soon as you edit the circuit, because it is then your circuit.

**Exercises that have a stored circuit:** all of them, including *Verification of logic gates*, *Simplify with Boolean algebra*, *Excess-3 to BCD*, *BCD to Excess-3*, *Full adder with 8:1 multiplexers (74153)*, *2-bit comparator with 74138 decoders*, the asynchronous up/down counters, the synchronous up/down counter and the 4-bit shift register.

---

## 8. Build a circuit with the AI (three modes)

The AI builds circuits in three ways. This needs the AI key from step 3 and **Demo mode switched off**. Open the **AI build** tab and choose a mode at the top.

Whichever mode you use, **the AI's circuit is only shown if the exact checker confirms it**. If its answer is wrong, it is told exactly what failed and tries again, up to 3 attempts.

### Mode 1: Describe it (no target, just words)

Use this when you only know what you want, not the exact function.

1. Choose **Describe it**.
2. Type the request in **What should the circuit do?** and press **Build from description**. For example:
   - `Build a half adder using logic gates`
   - `A circuit that outputs 1 when exactly two of three inputs are high`
   - `2-bit ripple up counter using a 7476`
   - `A 4-bit shift register with D flip-flops`
   - `SR flip flop using NAND gates` (a latch: gates wired in a feedback loop)
3. The AI works out the exact behaviour, writes it down as a **target**, and builds the circuit. The result box shows **Built to this target** (for example `S = A XOR B; Cout = A AND B`), the circuit appears on the workspace, and that target becomes your custom target, so **Validate** checks against it.
4. **Read the target line and make sure it is what you meant.** The circuit is checked against the AI's own reading of your request. That catches wiring mistakes, but it cannot tell whether the AI understood you. If the target is wrong, change your wording and build again, or edit the target in the **Target** tab.

### Mode 2: Build for target (the target is given)

Use this for an exercise or your own target: the AI builds a new circuit from scratch that matches it.

1. Pick an exercise in the dropdown, or set a **Custom target** (equation or truth table).
2. Choose **Build for target**. The **Target:** line shows what will be built.
3. Optionally type **extra instructions** about the design, for example `Use only NAND gates.` or `Use a 74138 and combine its outputs with NAND gates.`
4. Press **Build with AI**. You can also name a different circuit in the box (`full adder using 74153`) and the app switches to that exercise first.

If the AI fails, the stored circuit for that exercise is shown instead and labelled as a fallback. A custom target has no stored circuit, so you get an error message.

### Mode 3: Improve my circuit (build on what you have)

Use this when you already started a circuit and want the AI to finish or fix it.

1. Select the target (an exercise or a custom target) and build part of the circuit by hand.
2. Choose **Improve my circuit**.
3. Optionally say what should change, for example `add the carry output` or `fix the wiring`.
4. Press **Improve with AI**. The AI sees your circuit and what the checker says is wrong with it. It keeps your parts and positions and only adds, removes or rewires what is needed. New parts appear in a column to the right of yours.

If your circuit already matches the target and you typed nothing, the tab says so and changes nothing. If the AI cannot finish, **your circuit is left exactly as it was**; a stored circuit is never swapped in over your work.

### What the result box tells you

| Label | Meaning |
|---|---|
| **AI-generated and verified** (with the number of attempts and the model name) | The AI built it and it passed the check. |
| **Stored circuit (the AI could not finish)** | Modes 1 and 2 only: the AI failed, so a stored circuit is shown. The note says why. In mode 1 it is the stored circuit whose name matches your words. |
| **No change made** | Mode 3: nothing needed to change, or the AI could not improve it. |

**Tips:**

- A live attempt takes roughly 10 to 60 seconds, depending on the model and the task. The IC-heavy ones (74138 comparator, 74153 full adder) take longest; use Demo mode for those when presenting.
- Speed and reliability depend on `AI_MODEL` in `backend\.env`. Free models are often slow or get retired. A fast, inexpensive model works best, for example `anthropic/claude-haiku-5.5` on OpenRouter (needs credits). Restart the backend after changing it.
- Adjust the limits with `GENERATE_ATTEMPTS` (default `3`), `GENERATE_TIMEOUT_SECONDS` (default `240`) and `GENERATE_MAX_TOKENS` (default `16000`) in `backend\.env`. Models that "think" before answering use most of the token budget for thinking, so keep `GENERATE_MAX_TOKENS` high for them.

---

## 9. Run the tests (optional)

```powershell
cd backend
..\venv\Scripts\python.exe -m pytest
cd ..\frontend
npm test
npm run typecheck
```

Tests never call the real AI API, so they are free and work offline.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Frontend says **"Cannot reach the validation server"** | The backend isn't running, or isn't on port 8000. Start it (step 4). |
| **"Could not load exercises"** | Same as above. |
| AI section says **"AI feedback is not configured"** | No key was found. Check that `AI_API_KEY` is set in `backend\.env` (not `.env.example`), then restart the backend. |
| AI section says **"authentication failed"** | The key is wrong or revoked. Check it with your provider (OpenRouter: https://openrouter.ai/keys). The startup log's `ai_provider=` shows which provider the key was matched to; set `AI_PROVIDER` explicitly if it's wrong. |
| AI section says **"model ... was not found"** | Check `AI_MODEL`. OpenRouter IDs look like `vendor/model`, e.g. `anthropic/claude-opus-5`. |
| **AI build** shows **"Stored circuit (the AI could not finish)"** | The AI failed, so the safety net loaded the stored circuit. Read the note under the label: *"model ... was not found"* means `AI_MODEL` is wrong or retired; *"took too long"* means the model is slow (use a faster one, or Demo mode). |
| **Load demo** is greyed out | The exercise has no stored circuit, or you chose *Custom target*, or the backend is not reachable. Restart the backend, then reload the page. |
| Backtest prints **FAIL ... no golden circuit stored** | Regenerate the stored circuits with `cd backend; ..\venv\Scripts\python.exe -m app.tools.build_golden`, then run the backtest again. |
| AI section says **"insufficient credits"** | Add credits to your OpenRouter account. |
| AI section says **"rejected the request"** | The model may not support this request (for example, JSON output). Try a different `AI_MODEL`, or set `AI_RESPONSE_FORMAT=none`. |
| AI section says **"too many requests"** / **"temporarily unavailable"** | These are rate limits or provider issues. Wait and validate again; the circuit analysis is unaffected. |
| **`[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions`** | On Windows this usually means the port is already taken, often by another copy of the backend (including one started from Claude Code's preview pane). Find the owner with `Get-NetTCPConnection -LocalPort 8000 -State Listen` and stop that process (`Stop-Process -Id <OwningProcess>`). If nothing is listening, Windows may have reserved the port: check `netsh interface ipv4 show excludedportrange protocol=tcp` and use a port outside those ranges (see the next row). |
| **Port already in use** | Stop the other process, or use another port: `--port 8001` for the backend (then start the frontend with `$env:VITE_API_TARGET="http://127.0.0.1:8001"; npm run dev`). |
| `.env` changes have no effect | The backend reads `.env` at startup, so restart it. |
| Browser blocks the backend when the frontend runs on a different address | Add that address to `CORS_ORIGINS` in `backend\.env`. |

If you run the backend from Claude Code's preview, `.claude\launch.json` has the ready-made configurations `backend`, `backend-mock-ai`, and `frontend`.
