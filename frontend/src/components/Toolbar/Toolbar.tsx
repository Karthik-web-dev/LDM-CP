import type { Dispatch } from "react";
import type { EditorAction } from "../../circuit/editorReducer";
import "./Toolbar.css";

interface Props {
  dispatch: Dispatch<EditorAction>;
  onValidate: () => void;
  onHint: () => void;
  validating: boolean;
  hinting: boolean;
  canValidate: boolean;
  powered: boolean;
  onTogglePower: () => void;
  hasSequential: boolean;
  onLoadDemo: () => void;
  canLoadDemo: boolean;
  demoLoading: boolean;
  demoMode: boolean; // no AI calls while presenting
  hasClock: boolean; // the circuit contains a clock source
  clocksRunning: boolean;
  onToggleClocks: () => void;
}

/** Action bar above the workspace: clear, AI hint, validate, and the simulation power switch. */
export function Toolbar({ dispatch, onValidate, onHint, validating, hinting, canValidate, powered, onTogglePower, hasSequential, onLoadDemo, canLoadDemo, demoLoading, demoMode, hasClock, clocksRunning, onToggleClocks }: Props) {
  return (
    <div className="toolbar" role="toolbar" aria-label="Circuit actions">
      <button
        type="button"
        className="ghost"
        onClick={() => {
          if (confirm("Remove every component from the workspace?")) dispatch({ type: "clear" });
        }}
      >
        Clear
      </button>
      {hasSequential && (
        <button type="button" className="ghost" onClick={() => dispatch({ type: "resetSequential" })} title="Set every flip-flop and latch to 0">
          Reset flip-flops
        </button>
      )}
      {hasClock && (
        <button
          type="button"
          aria-pressed={clocksRunning}
          className={clocksRunning ? "primary" : ""}
          onClick={onToggleClocks}
          title="Start or stop every clock source at its own frequency"
        >
          {clocksRunning ? "Stop clocks" : "Run clocks"}
        </button>
      )}
      <span className="tool-divider" aria-hidden />
      <button
        type="button"
        onClick={onLoadDemo}
        disabled={!canLoadDemo || demoLoading}
        title="Place the stored, verified circuit for this exercise on the workspace and check it (no AI, no network needed)"
      >
        {demoLoading ? "Loading…" : "Load demo"}
      </button>
      <button type="button" onClick={onHint} disabled={hinting || !canValidate || demoMode} title={demoMode ? "Demo mode: the AI is not called" : "Ask the AI tutor for a nudge towards the next step"}>
        {hinting ? "Thinking…" : "Hint"}
      </button>
      <button type="button" className="primary" onClick={onValidate} disabled={validating || !canValidate}>
        {validating ? "Checking…" : "Validate"}
      </button>
      <button
        type="button"
        role="switch"
        aria-checked={powered}
        className={`power-switch ${powered ? "on" : ""}`}
        onClick={onTogglePower}
        title={powered ? "Simulation running. Click to stop." : "Simulation stopped. Click to start."}
      >
        <span className="power-o">O</span>
        <span className="power-knob" aria-hidden />
        <span className="power-i">I</span>
      </button>
    </div>
  );
}
