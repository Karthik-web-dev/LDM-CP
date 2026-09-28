import type { Dispatch } from "react";
import type { EditorAction } from "../../circuit/editorReducer";
import { GATE_ORDER, GATES } from "../../circuit/gateLibrary";
import { GateShape } from "../CircuitEditor/CircuitEditor";
import "./Toolbar.css";

interface Props {
  dispatch: Dispatch<EditorAction>;
  onValidate: () => void;
  onHint: () => void;
  validating: boolean;
  hinting: boolean;
  canValidate: boolean;
}

function GateIcon({ type }: { type: (typeof GATE_ORDER)[number] }) {
  const pins = GATES[type].defaultInputs;
  return (
    <svg viewBox="-2 -2 74 44" className="gate-icon" aria-hidden>
      <GateShape x={0} y={0} w={70} h={40} type={type} pins={pins} showLabel={false} />
    </svg>
  );
}

export function Toolbar({ dispatch, onValidate, onHint, validating, hinting, canValidate }: Props) {
  return (
    <div className="toolbar" role="toolbar" aria-label="Circuit tools">
      <div className="tool-group">
        <button type="button" className="tool-btn" onClick={() => dispatch({ type: "add", kind: "input" })} title="Add an input switch">
          <svg viewBox="0 0 24 24" className="io-icon" aria-hidden><rect x="3" y="7" width="14" height="10" rx="5" /><circle cx="8" cy="12" r="3" /><path d="M17 12h4" /></svg>
          Input
        </button>
        <button type="button" className="tool-btn" onClick={() => dispatch({ type: "add", kind: "output" })} title="Add an output lamp">
          <svg viewBox="0 0 24 24" className="io-icon" aria-hidden><path d="M3 12h5" /><circle cx="14" cy="12" r="6" /></svg>
          Output
        </button>
      </div>
      <span className="tool-divider" aria-hidden />
      <div className="tool-group gates">
        {GATE_ORDER.map((g) => (
          <button
            key={g}
            type="button"
            className="tool-btn gate-btn"
            onClick={() => dispatch({ type: "add", kind: "gate", gateType: g })}
            title={`Add ${g === "BUFFER" ? "a buffer" : `an ${g}`} gate`}
          >
            <GateIcon type={g} />
            <span>{g === "BUFFER" ? "BUF" : g}</span>
          </button>
        ))}
      </div>
      <div className="tool-group end">
        <button
          type="button"
          className="ghost"
          onClick={() => {
            if (confirm("Remove every component from the canvas?")) dispatch({ type: "clear" });
          }}
        >
          Clear
        </button>
        <button type="button" onClick={onHint} disabled={hinting || !canValidate} title="Ask the AI tutor for a nudge towards the next step">
          {hinting ? "Thinking…" : "Hint"}
        </button>
        <button type="button" className="primary" onClick={onValidate} disabled={validating || !canValidate}>
          {validating ? "Checking…" : "Validate"}
        </button>
      </div>
    </div>
  );
}
