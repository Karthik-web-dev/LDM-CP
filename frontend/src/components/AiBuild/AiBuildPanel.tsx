import { useState } from "react";
import type { BuildIntent, DemoEntry, GenerateResponse } from "../../api/validationApi";

interface Props {
  busy: boolean;
  demoMode: boolean;
  /** Which kind of build is selected (live mode only). */
  intent: BuildIntent;
  onIntent: (intent: BuildIntent) => void;
  /** Last generation result, or null before the first one. */
  result: GenerateResponse | null;
  error: string | null;
  /** There is a target (an exercise or a custom target) selected. */
  hasTarget: boolean;
  /** There is something on the workspace to build on. */
  hasCircuit: boolean;
  onGenerate: (prompt: string) => void;
  /** What the selected target is, shown so it is clear what will be built. */
  targetLabel: string;
  /** Stored circuits that demo mode can open, and a direct way to open one. */
  catalog: DemoEntry[];
  onPick: (taskId: string) => void;
}

const SOURCE_TEXT: Record<GenerateResponse["source"], string> = {
  ai: "AI-generated and verified",
  stored: "Stored demo circuit opened",
  fallback: "Stored circuit (the AI could not finish)",
  none: "Nothing generated",
};

const MODES: { id: BuildIntent; label: string; help: string }[] = [
  { id: "describe", label: "Describe it", help: "Say in plain words what you want. There is no target: the AI states exactly what it builds, and that becomes your target." },
  { id: "target", label: "Build for target", help: "Build a new circuit from scratch for the selected target." },
  { id: "extend", label: "Improve my circuit", help: "Build on the circuit already on the workspace so it meets the selected target. Your parts keep their places." },
];

const PROMPT_TEXT: Record<BuildIntent, { label: string; placeholder: string; rows: number }> = {
  describe: { label: "What should the circuit do?", placeholder: "A half adder using logic gates", rows: 3 },
  target: { label: "Extra instructions (optional)", placeholder: "For example: use only NAND gates", rows: 3 },
  extend: { label: "What should change? (optional)", placeholder: "For example: add the carry output", rows: 3 },
};

const BUTTON_TEXT: Record<BuildIntent, string> = { describe: "Build from description", target: "Build with AI", extend: "Improve with AI" };

/** Ask the AI to build a circuit three ways, or (in demo mode) open a stored one. Every AI answer is checked first. */
export function AiBuildPanel({ busy, demoMode, intent, onIntent, result, error, hasTarget, hasCircuit, onGenerate, targetLabel, catalog, onPick }: Props) {
  const [prompt, setPrompt] = useState("");
  const text = prompt.trim();
  const blocked = demoMode
    ? false
    : intent === "describe"
      ? !text
      : intent === "target"
        ? !hasTarget
        : !hasTarget || !hasCircuit;
  const why =
    demoMode || !blocked
      ? null
      : intent === "describe"
        ? "Describe the circuit first."
        : !hasTarget
          ? "Pick an exercise or set a custom target first."
          : "Put a circuit on the workspace first.";
  const mode = MODES.find((m) => m.id === intent)!;

  return (
    <div className="ai-build">
      {demoMode ? (
        <p className="demo-note">
          <b>Demo mode is on.</b> Type what you want, for example <i>half adder</i>, and the stored circuit opens instantly. The AI is not called.
        </p>
      ) : (
        <>
          <div className="segmented ai-modes" role="tablist" aria-label="How to build">
            {MODES.map((m) => (
              <button key={m.id} type="button" role="tab" aria-selected={intent === m.id} className={intent === m.id ? "active" : ""} onClick={() => onIntent(m.id)} disabled={busy}>
                {m.label}
              </button>
            ))}
          </div>
          <p className="ai-mode-help">{mode.help}</p>
          {intent !== "describe" && (
            <p className="ai-build-target">
              <b>Target:</b> {targetLabel}
              {intent === "target" && <span className="muted small"> (name another circuit in the box, such as "half adder", to switch to it)</span>}
            </p>
          )}
        </>
      )}
      <label className="ai-build-prompt">
        {demoMode ? "What should I open?" : PROMPT_TEXT[intent].label}
        <textarea
          rows={demoMode ? 2 : PROMPT_TEXT[intent].rows}
          maxLength={demoMode ? 300 : 1000}
          value={prompt}
          placeholder={demoMode ? "half adder, full adder using 74153, shift register…" : PROMPT_TEXT[intent].placeholder}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (demoMode && e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!busy) onGenerate(prompt);
            }
          }}
          disabled={busy}
        />
      </label>
      <button type="button" className="primary" onClick={() => onGenerate(prompt)} disabled={busy || blocked} title={why ?? undefined}>
        {busy ? "Working…" : demoMode ? "Open stored circuit" : BUTTON_TEXT[intent]}
      </button>
      {why && <p className="muted small">{why}</p>}

      {demoMode && catalog.length > 0 && (
        <div className="demo-catalog">
          <div className="demo-catalog-title">Stored circuits (click one to open it)</div>
          <div className="demo-chips">
            {catalog.map((entry) => (
              <button key={entry.task_id} type="button" className="demo-chip" onClick={() => onPick(entry.task_id)} disabled={busy}>
                {entry.title}
                <span className="demo-chip-style">{entry.style === "ic" ? "IC" : "gates"}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <p className="check bad">{error}</p>}
      {result && !busy && (
        <div className={`ai-build-result ${result.success ? "ok" : "bad"}`}>
          <div className="ai-build-source">
            {result.source === "none" && result.success ? "No change made" : SOURCE_TEXT[result.source]}
            {result.source === "ai" && ` · ${result.attempts} attempt${result.attempts === 1 ? "" : "s"}`}
            {result.model && <span className="muted small"> · {result.model}</span>}
          </div>
          {result.explanation && <p>{result.explanation}</p>}
          {result.spec && (
            <p className="ai-spec">
              <b>Built to this target:</b> <code>{specText(result.spec)}</code>
            </p>
          )}
          {result.notice && <p className="muted small">{result.notice}</p>}
        </div>
      )}
    </div>
  );
}

/** The target the AI says it built to, in one readable line. */
function specText(spec: NonNullable<GenerateResponse["spec"]>): string {
  if (spec.sequence) {
    const steps = spec.sequence.steps.length;
    return `behaviour checked over ${steps} step${steps === 1 ? "" : "s"}${spec.sequence.clock ? ` (one ${spec.sequence.clock} pulse each)` : ""}, outputs ${spec.outputs.join(", ")}`;
  }
  if (spec.expected_truth_table) return `truth table for ${Object.keys(spec.expected_truth_table).join(", ")} over ${spec.inputs.join(", ")}`;
  const equations = Object.entries(spec.expected_outputs ?? { [spec.outputs[0] ?? "Y"]: spec.expected_expression ?? "" });
  return equations.map(([label, expr]) => `${label} = ${expr}`).join("; ");
}
