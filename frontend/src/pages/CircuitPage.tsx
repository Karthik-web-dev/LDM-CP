import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { fetchTasks, outputLabels, validateCircuit, type AIFeedback, type AIMode, type Target, type Task, type ValidateResponse } from "../api/validationApi";
import { serializeCircuit } from "../circuit/circuitSerializer";
import type { EditorState } from "../circuit/circuitTypes";
import { editorReducer, emptyEditorState } from "../circuit/editorReducer";
import { simulate } from "../circuit/simulator";
import { CircuitEditor, type Selection } from "../components/CircuitEditor/CircuitEditor";
import { ErrorMessage } from "../components/ErrorMessage/ErrorMessage";
import { KMapPanel } from "../components/KMap/KMap";
import { TargetEditor } from "../components/TargetEditor/TargetEditor";
import { CUSTOM_TASK_ID, defaultDraft, type TargetDraft } from "../components/TargetEditor/targetDraft";
import { TaskPanel } from "../components/TaskPanel/TaskPanel";
import { Inspector } from "../components/Toolbar/Inspector";
import { Toolbar } from "../components/Toolbar/Toolbar";
import { ValidationPanel, type Phase } from "../components/ValidationPanel/ValidationPanel";

const circuitKey = (taskId: string) => `ldm.circuit.${taskId}`;
const LAST_TASK_KEY = "ldm.lastTask";
const CUSTOM_TASK_KEY = "ldm.customTask";
const CUSTOM_DRAFT_KEY = "ldm.customDraft";

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

type Tab = "target" | "results" | "json";

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
  const signals = useMemo(() => simulate(state), [state]);
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
  };

  const scaffold = (t: Task) => dispatch({ type: "scaffold", inputs: t.inputs, outputs: t.outputs.length ? t.outputs : outputLabels(t) });

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

  const onValidate = async () => {
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
      if (!det.structurally_valid || det.errors.length) {
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

  return (
    <div className="app">
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
          />
          <Inspector state={state} selection={selection} dispatch={dispatch} onClear={() => setSelection(null)} />
          <CircuitEditor
            state={state}
            dispatch={dispatch}
            signals={signals}
            selection={selection}
            onSelect={(s) => { setSelection(s); setFocusIds(new Set()); }}
            errorIds={errorIds}
            focusIds={focusIds}
          />
        </section>

        <aside className="side-pane">
          <div className="tabs" role="tablist">
            {(["target", "results", "json"] as Tab[]).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
                {t === "target" ? "Target" : t === "results" ? "Validation" : "Circuit JSON"}
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
                    <KMapPanel target={target} version={String(taskId)} />
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
