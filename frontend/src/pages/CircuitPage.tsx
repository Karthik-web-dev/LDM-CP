import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { fetchDemoCatalog, fetchGolden, fetchTasks, generateCircuit, matchDemo, outputLabels, validateCircuit, type AIFeedback, type AIMode, type BuildIntent, type DemoEntry, type GenerateResponse, type Target, type Task, type ValidateResponse } from "../api/validationApi";
import { deserializeCircuit, serializeCircuit } from "../circuit/circuitSerializer";
import type { EditorState, NormalizedCircuit } from "../circuit/circuitTypes";
import { editorReducer, emptyEditorState } from "../circuit/editorReducer";
import { clockHalfPeriodMs } from "../circuit/gateLibrary";
import { hasSequential, simulate } from "../circuit/simulator";
import { CircuitEditor, type Selection } from "../components/CircuitEditor/CircuitEditor";
import { AiBuildPanel } from "../components/AiBuild/AiBuildPanel";
import { ErrorMessage } from "../components/ErrorMessage/ErrorMessage";
import { KMapPanel } from "../components/KMap/KMap";
import { TargetEditor } from "../components/TargetEditor/TargetEditor";
import { CUSTOM_TASK_ID, defaultDraft, type TargetDraft } from "../components/TargetEditor/targetDraft";
import { TaskPanel } from "../components/TaskPanel/TaskPanel";
import { PartsBin } from "../components/PartsBin/PartsBin";
import { Inspector } from "../components/Toolbar/Inspector";
import { Toolbar } from "../components/Toolbar/Toolbar";
import { ValidationPanel, type Phase } from "../components/ValidationPanel/ValidationPanel";

const circuitKey = (taskId: string) => `ldm.circuit.${taskId}`;
const LAST_TASK_KEY = "ldm.lastTask";
const CUSTOM_TASK_KEY = "ldm.customTask";
const CUSTOM_DRAFT_KEY = "ldm.customDraft";
const DEMO_MODE_KEY = "ldm.demoMode";

function load<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, typeof value === "string" ? value : JSON.stringify(value));
  } catch {
    /* storage unavailable: persistence is a convenience only */
  }
}

/** The semantic content of a circuit: positions excluded, so moving parts does not mark results stale. */
function semanticKey(state: EditorState): string {
  const c = serializeCircuit(state);
  const strip = <T extends { position?: unknown }>(items: T[]) => items.map(({ position: _p, ...rest }) => rest);
  return JSON.stringify({ ...c, inputs: strip(c.inputs), gates: strip(c.gates), outputs: strip(c.outputs) });
}

/** Turn an exercise into an editable equation draft ("edit a copy"). */
function draftFromExercise(task: Task): TargetDraft {
  const draft = defaultDraft();
  if (task.expected_truth_table) {
    return { ...draft, mode: "table", tableInputs: task.inputs, tableOutputs: Object.keys(task.expected_truth_table), cells: task.expected_truth_table };
  }
  const equations = task.expected_outputs
    ? Object.entries(task.expected_outputs).map(([label, expr]) => ({ label, expr }))
    : [{ label: outputLabels(task)[0], expr: task.expected_expression ?? "" }];
  return { ...draft, mode: "equation", equations };
}

type Tab = "target" | "results" | "ai" | "json";

/** The clock input of a task with memory, if it has one (latches have none). */
const clockOf = (t: Task | null | undefined): string | undefined => t?.sequence?.clock ?? undefined;

/** One line saying what the selected target is, so it is clear what the AI will build. */
function describeTarget(task: Task | null): string {
  if (!task) return "No target selected";
  if (task.sequence) return `${task.title || task.id} (behaviour checked step by step)`;
  if (task.expected_truth_table) return `${task.title || "Custom target"} (truth table for ${Object.keys(task.expected_truth_table).join(", ")})`;
  const equations = Object.entries(task.expected_outputs ?? { [task.outputs[0] ?? "Y"]: task.expected_expression ?? "" });
  const text = equations.map(([label, expr]) => `${label} = ${expr}`).join("; ");
  return task.title ? `${task.title}: ${text}` : `Custom target: ${text}`;
}

export function CircuitPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [customTask, setCustomTask] = useState<Task | null>(() => load<Task>(CUSTOM_TASK_KEY));
  const [draft, setDraft] = useState<TargetDraft>(() => load<TargetDraft>(CUSTOM_DRAFT_KEY) ?? defaultDraft());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [state, dispatch] = useReducer(editorReducer, undefined, emptyEditorState);
  const [selection, setSelection] = useState<Selection>(null);
  const [focusIds, setFocusIds] = useState<Set<string>>(new Set());
  const [tab, setTab] = useState<Tab>("results");

  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<ValidateResponse | null>(null);
  const [ai, setAi] = useState<AIFeedback | null>(null);
  const [aiMode, setAiMode] = useState<AIMode>("feedback");
  const [validateError, setValidateError] = useState<string | null>(null);
  const [validatedKey, setValidatedKey] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const isCustom = taskId === CUSTOM_TASK_ID;
  const task = isCustom ? customTask : (tasks.find((t) => t.id === taskId) ?? null);
  // Demo mode: no AI calls anywhere (validation, hints, building), so a presentation cannot depend on the network.
  const [demoMode, setDemoMode] = useState<boolean>(() => load<boolean>(DEMO_MODE_KEY) === true);
  const [buildIntent, setBuildIntent] = useState<BuildIntent>("target");
  const [building, setBuilding] = useState(false);
  const [buildResult, setBuildResult] = useState<GenerateResponse | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<DemoEntry[]>([]);
  const [demo, setDemo] = useState<{ source: string; key: string; title?: string } | null>(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const [autoValidate, setAutoValidate] = useState(false);
  const [powered, setPowered] = useState(true);
  // Inputs being clocked right now (clock sources at their frequency, other inputs at 1 Hz).
  const [running, setRunning] = useState<Record<string, boolean>>({});
  // With the power switch off nothing is simulated: every wire and lamp shows as unknown.
  const signals = useMemo(() => (powered ? simulate(state) : new Map<string, boolean | undefined>()), [state, powered]);
  const normalized = useMemo(() => serializeCircuit(state), [state]);
  const currentKey = useMemo(() => semanticKey(state), [state]);
  const target: Target | null = !task ? null : isCustom ? { task: customTask! } : { taskId: taskId! };

  const resetResults = () => {
    abortRef.current?.abort();
    setResult(null);
    setAi(null);
    setValidateError(null);
    setPhase("idle");
    setFocusIds(new Set());
    setRunning({}); // never carry a running clock into another circuit
  };

  const scaffold = (t: Task) =>
    dispatch({ type: "scaffold", inputs: t.inputs, outputs: t.outputs.length ? t.outputs : outputLabels(t), clock: clockOf(t) });

  const openTask = (id: string, list: Task[], custom: Task | null) => {
    const target = id === CUSTOM_TASK_ID ? custom : list.find((x) => x.id === id);
    if (id !== CUSTOM_TASK_ID && !target) return;
    resetResults();
    setTaskId(id);
    save(LAST_TASK_KEY, JSON.stringify(id));
    setSelection(null);
    const saved = load<EditorState>(circuitKey(id));
    if (saved) {
      dispatch({ type: "load", state: saved });
    } else {
      dispatch({ type: "clear" });
      if (target) scaffold(target);
    }
    setTab(id === CUSTOM_TASK_ID && !custom ? "target" : "results");
  };

  useEffect(() => {
    // The demo button and the list of stored circuits; a failure just hides them.
    fetchDemoCatalog().then(setCatalog).catch(() => setCatalog([]));
  }, []);

  useEffect(() => {
    fetchTasks()
      .then((list) => {
        setTasks(list);
        const last = load<string>(LAST_TASK_KEY);
        const first = last === CUSTOM_TASK_ID || list.some((t) => t.id === last) ? last! : list[0]?.id;
        if (first) openTask(first, list, load<Task>(CUSTOM_TASK_KEY));
      })
      .catch((e: Error) => setLoadError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Autosave the circuit per target, and the custom target draft.
  useEffect(() => {
    if (taskId) save(circuitKey(taskId), state);
  }, [state, taskId]);
  useEffect(() => save(CUSTOM_DRAFT_KEY, draft), [draft]);

  // Delete key removes the selected part (unless typing in a field).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) return;
      if ((e.key === "Delete" || e.key === "Backspace") && selection) {
        e.preventDefault();
        dispatch(selection.kind === "wire" ? { type: "removeWire", id: selection.id } : { type: "remove", id: selection.id });
        setSelection(null);
      } else if (e.key === "Escape") {
        setSelection(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selection]);

  const applyCustomTarget = (t: Task) => {
    setCustomTask(t);
    save(CUSTOM_TASK_KEY, t);
    resetResults();
    setTaskId(CUSTOM_TASK_ID);
    save(LAST_TASK_KEY, JSON.stringify(CUSTOM_TASK_ID));
    scaffold(t);
  };

  /** Put a generated or stored circuit on the workspace and check it (without any AI call). */
  const placeCircuit = (circuit: NormalizedCircuit, source: string, title?: string, clock?: string | string[]) => {
    const base = deserializeCircuit(circuit);
    // Clock inputs (the clock of a sequential exercise, or clocks already on the workspace) stay real clock sources.
    const clockLabels = new Set(typeof clock === "string" ? [clock] : (clock ?? []));
    const next: EditorState = clockLabels.size
      ? { ...base, components: base.components.map((c) => (c.kind === "input" && c.label && clockLabels.has(c.label) ? { ...c, clockHz: c.clockHz ?? 1 } : c)) }
      : base;
    resetResults();
    setSelection(null);
    dispatch({ type: "load", state: next });
    setDemo({ source, key: semanticKey(next), title });
    setAutoValidate(true);
  };

  const changeDemoMode = (on: boolean) => {
    setDemoMode(on);
    save(DEMO_MODE_KEY, on);
  };

  const titleOf = (id: string) => tasks.find((t) => t.id === id)?.title ?? id;

  /**
   * Open the stored circuit for exercise `id`. The workspace switches to that exercise first, so the
   * circuit is checked against its own target whichever exercise was selected before.
   */
  const showStored = async (id: string, note?: string) => {
    const golden = await fetchGolden(id);
    if (id !== taskId) openTask(id, tasks, customTask);
    placeCircuit(golden.circuit, golden.source, titleOf(id), clockOf(tasks.find((t) => t.id === id)));
    setTab("results");
    setBuildResult({
      success: true, source: "stored", circuit: golden.circuit, attempts: 0, model: null,
      explanation: `Opened the stored circuit for "${titleOf(id)}".`, notice: note ?? null,
    });
  };

  /** Open a stored circuit chosen from the list in the AI build tab. */
  const pickStored = async (id: string) => {
    setBuilding(true);
    setBuildError(null);
    try {
      await showStored(id);
    } catch (e) {
      setBuildError((e as Error).message);
    } finally {
      setBuilding(false);
    }
  };

  /**
   * Demo mode: what was typed ("half adder") is matched to a stored circuit by deterministic text
   * matching, and that circuit is opened. Live mode: the AI builds it (verified, with retries); a
   * clearly named exercise in the text switches the workspace to that exercise first.
   */
  const buildWithAi = async (prompt: string) => {
    const text = prompt.trim();
    setBuilding(true);
    setBuildError(null);
    setBuildResult(null);
    try {
      if (demoMode) {
        let id = taskId && !isCustom ? taskId : null;
        let note: string | undefined;
        if (text) {
          const found = await matchDemo(text);
          if (!found.best) {
            const hints = found.matches.map((m) => m.title).join(", ");
            setBuildResult({
              success: false, source: "none", circuit: null, explanation: null, attempts: 0, model: null,
              notice: `No stored circuit matches "${text}".${hints ? ` Did you mean: ${hints}?` : " Pick one from the list below."}`,
            });
            return;
          }
          id = found.best.task_id;
          note = `Matched "${text}" to ${found.best.title} (${found.best.style === "ic" ? "uses an IC" : "basic gates"}).`;
        }
        if (!id) {
          setBuildError("Type what to open, or pick an exercise first.");
          return;
        }
        await showStored(id, note);
        return;
      }

      if (buildIntent === "describe") {
        // No target: the AI works out what to build from the words, and the target it built to becomes ours.
        if (!text) {
          setBuildError("Describe the circuit you want first.");
          return;
        }
        const response = await generateCircuit(null, text, "live", undefined, { intent: "describe" });
        setBuildResult(response);
        if (response.circuit && response.spec) {
          applyCustomTarget(response.spec);
          if (!response.spec.sequence) setDraft(draftFromExercise(response.spec));
          placeCircuit(response.circuit, "ai", response.spec.title, clockOf(response.spec));
        } else if (response.circuit && response.matched_task_id) {
          const id = response.matched_task_id;
          openTask(id, tasks, customTask);
          placeCircuit(response.circuit, "fallback", titleOf(id), clockOf(tasks.find((t) => t.id === id)));
        }
        return;
      }

      if (buildIntent === "extend") {
        // Build on what is on the workspace; the AI must keep the target satisfied.
        if (!target) {
          setBuildError("Pick an exercise or set a custom target first.");
          return;
        }
        const clocks = state.components.filter((c) => c.kind === "input" && c.clockHz !== undefined && c.label).map((c) => c.label!);
        const response = await generateCircuit(target, text, "live", undefined, { intent: "extend", circuit: serializeCircuit(state) });
        setBuildResult(response);
        const exerciseClock = clockOf(task);
        if (response.circuit) placeCircuit(response.circuit, "ai", task?.title, exerciseClock ? [...clocks, exerciseClock] : clocks);
        return;
      }

      let liveTarget = target;
      let switchNote: string | null = null;
      if (text) {
        // A circuit named in the text (for example "full adder using 74153") selects that exercise.
        const found = await matchDemo(text, true).catch(() => null);
        if (found?.best && found.best.task_id !== taskId) {
          liveTarget = { taskId: found.best.task_id };
          switchNote = `Your request matched "${found.best.title}", so that exercise's target was used${isCustom ? " instead of your custom target" : ""}.`;
          openTask(found.best.task_id, tasks, customTask);
        }
      }
      if (!liveTarget) return;
      const response = await generateCircuit(liveTarget, prompt, "live");
      setBuildResult({ ...response, notice: [switchNote, response.notice].filter(Boolean).join(" ") || null });
      if (response.circuit) {
        const builtFor = "taskId" in liveTarget ? tasks.find((t) => t.id === liveTarget.taskId) : liveTarget.task;
        placeCircuit(response.circuit, response.source === "ai" ? "ai" : "fallback", builtFor?.title, clockOf(builtFor));
      }
    } catch (e) {
      setBuildError((e as Error).message);
    } finally {
      setBuilding(false);
    }
  };

  /** Place the stored circuit for this exercise on the workspace, then check it without any AI call. */
  const loadDemo = async () => {
    if (!taskId || isCustom) return;
    setDemoLoading(true);
    try {
      const golden = await fetchGolden(taskId);
      placeCircuit(golden.circuit, golden.source, golden.title, clockOf(task));
    } catch (e) {
      setValidateError((e as Error).message);
      setTab("results");
    } finally {
      setDemoLoading(false);
    }
  };

  // Validate once the demo circuit is in the editor state (this runs after the re-render).
  useEffect(() => {
    if (!autoValidate) return;
    setAutoValidate(false);
    void runValidate(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoValidate]);

  const onValidate = () => runValidate(demoMode);

  const runValidate = async (skipAi: boolean) => {
    if (!taskId) return;
    if (isCustom && !customTask) {
      setTab("target");
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const circuit = serializeCircuit(state);
    const key = semanticKey(state);
    setTab("results");
    setAiMode("feedback");
    setValidateError(null);
    setAi(null);
    setFocusIds(new Set());
    setPhase("analyzing");
    try {
      // Stage 1: exact analysis only; fast, so results appear immediately.
      const analysis = await validateCircuit(target!, circuit, false, controller.signal);
      setResult(analysis);
      setValidatedKey(key);
      const det = analysis.deterministic;
      if (!det.structurally_valid || det.errors.length || skipAi) {
        setAi(analysis.ai);
        setPhase("done");
        return;
      }
      // Stage 2: AI tutor feedback (the UI stays interactive meanwhile).
      setPhase("feedback");
      const full = await validateCircuit(target!, circuit, true, controller.signal);
      setAi(full.ai);
      setPhase("done");
    } catch (e) {
      if (controller.signal.aborted) return;
      setValidateError((e as Error).message);
      setPhase("done");
    }
  };

  /** Ask the tutor for a nudge. Works for empty or unfinished circuits too. */
  const onHint = async () => {
    if (!target) {
      setTab("target");
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const key = semanticKey(state);
    setTab("results");
    setAiMode("hint");
    setValidateError(null);
    setAi(null);
    setPhase("feedback");
    try {
      const response = await validateCircuit(target, serializeCircuit(state), true, controller.signal, "hint");
      setResult(response);
      setValidatedKey(key);
      setAi(response.ai);
      setPhase("done");
    } catch (e) {
      if (controller.signal.aborted) return;
      setValidateError((e as Error).message);
      setPhase("done");
    }
  };

  const errorIds = useMemo(() => {
    if (!result || validatedKey !== currentKey) return new Set<string>();
    return new Set(result.deterministic.errors.flatMap((i) => [i.component, ...i.related]).filter((x): x is string => !!x));
  }, [result, validatedKey, currentKey]);

  const focus = (ids: string[]) => {
    setFocusIds(new Set(ids));
    if (ids.length === 1) setSelection({ kind: "component", id: ids[0] });
  };

  const exercise = !isCustom ? task : null;
  const sequential = !!task?.sequence;

  // Running clocks: each toggles its input every half period (two toggles = one full pulse).
  const clockPlan = state.components
    .filter((c) => c.kind === "input" && running[c.id])
    .map((c) => `${c.id}@${c.clockHz ?? 1}`)
    .join(",");
  useEffect(() => {
    if (!clockPlan) return;
    const timers = clockPlan.split(",").map((entry) => {
      const [id, hz] = entry.split("@");
      return setInterval(() => dispatch({ type: "toggleInput", id }), clockHalfPeriodMs(Number(hz)));
    });
    return () => timers.forEach(clearInterval);
  }, [clockPlan]);

  const clockIds = state.components.filter((c) => c.kind === "input" && c.clockHz !== undefined).map((c) => c.id);
  const clocksRunning = clockIds.some((id) => running[id]);
  const toggleRun = (id: string) => setRunning((r) => ({ ...r, [id]: !r[id] }));
  const toggleClocks = () => setRunning((r) => ({ ...r, ...Object.fromEntries(clockIds.map((id) => [id, !clocksRunning])) }));

  return (
    <div className="app">
      <div className="titlebar">
        <span className="titlebar-name">LDM Circuit Lab</span>
        <span className="titlebar-doc">{task ? `- [${task.title ?? task.id}]` : ""}</span>
        <label className="titlebar-demo" title="Demo mode: never call the AI. Stored circuits are used and results are checked offline.">
          <input type="checkbox" checked={demoMode} onChange={(e) => changeDemoMode(e.target.checked)} /> Demo mode
        </label>
      </div>
      <header className="app-header">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden>
            <rect width="32" height="32" rx="8" fill="currentColor" />
            <path d="M9 9h7a7 7 0 0 1 0 14H9z" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
            <path d="M23 16h4M5 12.5h4M5 19.5h4" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
          </svg>
          <div>
            <h1 className="brand-name">Circuit Lab</h1>
            <div className="brand-sub">Logic design validator</div>
          </div>
        </div>
        {tasks.length > 0 && (
          <TaskPanel
            tasks={tasks}
            selectedId={taskId}
            task={task}
            onSelect={(id) => openTask(id, tasks, customTask)}
            onScaffold={() => task && scaffold(task)}
            onEditTarget={() => setTab("target")}
          />
        )}
      </header>
      {loadError && <ErrorMessage message={`Could not load exercises: ${loadError}`} />}

      <main className="workspace">
        <section className="editor-pane" aria-label="Circuit editor">
          <Toolbar
            dispatch={dispatch}
            onValidate={onValidate}
            onHint={onHint}
            validating={phase === "analyzing"}
            hinting={phase === "feedback" && aiMode === "hint"}
            canValidate={!!task}
            powered={powered}
            onTogglePower={() => setPowered((p) => !p)}
            hasSequential={hasSequential(state)}
            onLoadDemo={loadDemo}
            canLoadDemo={!!taskId && !isCustom && catalog.some((e) => e.task_id === taskId)}
            demoLoading={demoLoading}
            demoMode={demoMode}
            hasClock={clockIds.length > 0}
            clocksRunning={clocksRunning}
            onToggleClocks={toggleClocks}
          />
          {demo && demo.key === currentKey && (
            <div className="demo-tag" role="status">
              {demo.source === "ai"
                ? "AI-generated circuit, checked against the exercise"
                : demo.source === "fallback"
                  ? "Stored circuit (the AI could not finish)"
                  : "Stored reference circuit"}
              {demo.title ? ` for "${demo.title}"` : ""}. Edit it to make it your own.
            </div>
          )}
          <div className="editor-body">
            <PartsBin dispatch={dispatch} />
            <div className="editor-main">
              <Inspector state={state} selection={selection} dispatch={dispatch} onClear={() => setSelection(null)} running={running} onToggleRun={toggleRun} />
              <CircuitEditor
                state={state}
                dispatch={dispatch}
                signals={signals}
                selection={selection}
                onSelect={(s) => { setSelection(s); setFocusIds(new Set()); }}
                errorIds={errorIds}
                focusIds={focusIds}
                running={running}
              />
            </div>
          </div>
        </section>

        <aside className="side-pane">
          <div className="tabs" role="tablist">
            {(["target", "results", "ai", "json"] as Tab[]).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
                {t === "target" ? "Target" : t === "results" ? "Validation" : t === "ai" ? "AI build" : "Circuit JSON"}
              </button>
            ))}
          </div>
          <div className="side-content">
            {tab === "target" && (isCustom ? (
              <TargetEditor draft={draft} onDraftChange={setDraft} activeTask={customTask} onApply={applyCustomTarget} />
            ) : (
              <div className="exercise-target">
                {exercise && (
                  <>
                    <p>This exercise's target is fixed. To validate against your own function, switch to <b>Custom target</b>.</p>
                    {!sequential && <KMapPanel target={target} version={String(taskId)} />}
                    <button
                      type="button"
                      onClick={() => {
                        setDraft(draftFromExercise(exercise));
                        openTask(CUSTOM_TASK_ID, tasks, customTask);
                        setTab("target");
                      }}
                    >
                      Edit a copy of this exercise as my own target
                    </button>
                  </>
                )}
              </div>
            ))}
            {tab === "results" && (
              <ValidationPanel
                phase={phase}
                result={result}
                ai={ai}
                aiMode={aiMode}
                error={validateError}
                stale={!!result && validatedKey !== currentKey}
                onFocus={focus}
                onHint={onHint}
                kmapTarget={target}
                circuit={normalized}
                circuitVersion={`${taskId}|${JSON.stringify(task)}|${currentKey}`}
                sequential={sequential}
              />
            )}
            {tab === "ai" && (
              <AiBuildPanel
                busy={building}
                demoMode={demoMode}
                result={buildResult}
                error={buildError}
                targetLabel={describeTarget(task)}
                intent={buildIntent}
                onIntent={setBuildIntent}
                hasTarget={!!task}
                hasCircuit={state.components.length > 0}
                onGenerate={buildWithAi}
                catalog={catalog}
                onPick={pickStored}
              />
            )}
            {tab === "json" && (
              <div className="json-debug">
                <p className="muted">This normalized JSON is what gets sent to the backend when you press Validate.</p>
                <pre>{JSON.stringify(normalized, null, 2)}</pre>
              </div>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}
