import type { Dispatch } from "react";
import type { EditorAction } from "../../circuit/editorReducer";
import type { EditorState, GateType } from "../../circuit/circuitTypes";
import { GATES, GATE_ORDER } from "../../circuit/gateLibrary";
import type { Selection } from "../CircuitEditor/CircuitEditor";

const LABEL_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
const RESERVED = new Set(["AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR"]);

export function labelProblem(label: string): string | null {
  if (!label) return "Label is required";
  if (!LABEL_RE.test(label)) return "Use letters, digits, _ (start with a letter)";
  if (RESERVED.has(label.toUpperCase())) return "Operator names can't be labels";
  return null;
}

interface Props {
  state: EditorState;
  selection: Selection;
  dispatch: Dispatch<EditorAction>;
  onClear: () => void;
}

export function Inspector({ state, selection, dispatch, onClear }: Props) {
  if (!selection) {
    return (
      <div className="inspector muted">
        Drag from a pin to another pin to connect. Click an input to toggle it. Select a part to edit it, and press Delete to remove it.
      </div>
    );
  }

  if (selection.kind === "wire") {
    const w = state.wires.find((x) => x.id === selection.id);
    if (!w) return <div className="inspector" />;
    return (
      <div className="inspector">
        <span>
          Wire <code>{w.from}</code> → <code>{w.to}</code>
          {w.to.startsWith("gate_") ? ` (input ${w.pin + 1})` : ""}
        </span>
        <button type="button" className="danger" onClick={() => { dispatch({ type: "removeWire", id: w.id }); onClear(); }}>
          Delete wire
        </button>
      </div>
    );
  }

  const c = state.components.find((x) => x.id === selection.id);
  if (!c) return <div className="inspector" />;
  const remove = () => { dispatch({ type: "remove", id: c.id }); onClear(); };

  if (c.kind === "gate") {
    const spec = GATES[c.gateType!];
    return (
      <div className="inspector">
        <code>{c.id}</code>
        <label>
          Type
          <select value={c.gateType} onChange={(e) => dispatch({ type: "setGateType", id: c.id, gateType: e.target.value as GateType })}>
            {GATE_ORDER.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </label>
        {spec.maxInputs > spec.minInputs && (
          <label>
            Inputs
            <input
              type="number"
              min={spec.minInputs}
              max={spec.maxInputs}
              value={c.pinCount}
              onChange={(e) => {
                const n = Math.min(spec.maxInputs, Math.max(spec.minInputs, Number(e.target.value) || spec.minInputs));
                dispatch({ type: "setPinCount", id: c.id, pinCount: n });
              }}
            />
          </label>
        )}
        <button type="button" className="danger" onClick={remove}>Delete gate</button>
      </div>
    );
  }

  const problem = labelProblem(c.label ?? "");
  const duplicate = state.components.some((o) => o.kind === c.kind && o.id !== c.id && o.label === c.label);
  return (
    <div className="inspector">
      <code>{c.id}</code>
      <label>
        {c.kind === "input" ? "Input" : "Output"} label
        <input
          type="text"
          value={c.label ?? ""}
          maxLength={32}
          onChange={(e) => dispatch({ type: "setLabel", id: c.id, label: e.target.value.trim() })}
          aria-invalid={!!problem || duplicate}
        />
      </label>
      {(problem || duplicate) && <span className="field-error">{problem ?? "Another component already uses this label"}</span>}
      {c.kind === "input" && (
        <button type="button" onClick={() => dispatch({ type: "toggleInput", id: c.id })}>
          Set to {state.inputValues[c.id] ? "0" : "1"}
        </button>
      )}
      <button type="button" className="danger" onClick={remove}>Delete {c.kind}</button>
    </div>
  );
}
