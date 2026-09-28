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

## 7. Run the tests (optional)

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
| AI section says **"insufficient credits"** | Add credits to your OpenRouter account. |
| AI section says **"rejected the request"** | The model may not support this request (for example, JSON output). Try a different `AI_MODEL`, or set `AI_RESPONSE_FORMAT=none`. |
| AI section says **"too many requests"** / **"temporarily unavailable"** | These are rate limits or provider issues. Wait and validate again; the circuit analysis is unaffected. |
| **`[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions`** | On Windows this usually means the port is already taken, often by another copy of the backend (including one started from Claude Code's preview pane). Find the owner with `Get-NetTCPConnection -LocalPort 8000 -State Listen` and stop that process (`Stop-Process -Id <OwningProcess>`). If nothing is listening, Windows may have reserved the port: check `netsh interface ipv4 show excludedportrange protocol=tcp` and use a port outside those ranges (see the next row). |
| **Port already in use** | Stop the other process, or use another port: `--port 8001` for the backend (then start the frontend with `$env:VITE_API_TARGET="http://127.0.0.1:8001"; npm run dev`). |
| `.env` changes have no effect | The backend reads `.env` at startup, so restart it. |
| Browser blocks the backend when the frontend runs on a different address | Add that address to `CORS_ORIGINS` in `backend\.env`. |

If you run the backend from Claude Code's preview, `.claude\launch.json` has the ready-made configurations `backend`, `backend-mock-ai`, and `frontend`.
