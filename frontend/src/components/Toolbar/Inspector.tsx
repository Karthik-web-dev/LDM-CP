import type { Dispatch } from "react";
import type { EditorAction } from "../../circuit/editorReducer";
import type { EditorState, GateType } from "../../circuit/circuitTypes";
import { BLOCK_ORDER, CLOCK_HZ_OPTIONS, GATES, GATE_ORDER, IC_ORDER, SOURCE_ORDER, gateLabel } from "../../circuit/gateLibrary";
import type { Selection } from "../CircuitEditor/CircuitEditor";

const LABEL_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
const RESERVED = new Set(["AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR"]);

function labelProblem(label: string): string | null {
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
  /** Inputs that are being clocked automatically (by id), and a way to start or stop one. */
  running: Record<string, boolean>;
  onToggleRun: (id: string) => void;
}

export function Inspector({ state, selection, dispatch, onClear, running, onToggleRun }: Props) {
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
          Wire <code>{w.from}{w.fromPin ? `.out${w.fromPin + 1}` : ""}</code> → <code>{w.to}</code>
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
            <optgroup label="Logic gates">
              {GATE_ORDER.map((g) => <option key={g} value={g}>{g}</option>)}
            </optgroup>
            <optgroup label="Sources">
              {SOURCE_ORDER.map((g) => <option key={g} value={g}>{g}</option>)}
            </optgroup>
            <optgroup label="74xx ICs">
              {IC_ORDER.map((g) => <option key={g} value={g}>{g}</option>)}
            </optgroup>
            <optgroup label="Combinational blocks">
              {BLOCK_ORDER.map((g) => <option key={g} value={g}>{gateLabel(g)}</option>)}
            </optgroup>
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
        {spec.block?.description && <span className="muted small">{spec.block.description}.</span>}
        {spec.sequential && (
          <span className="muted small">
            Starts at 0. /PRE and /CLR are active low; tie unused pins to VCC. Use Pulse on the clock input to step it.
          </span>
        )}
        {spec.block && <span className="muted small">{spec.block.inputNames.join(", ")} → {spec.block.outputNames.join(", ")}</span>}
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
        <>
          <button type="button" onClick={() => dispatch({ type: "toggleInput", id: c.id })}>
            Set to {state.inputValues[c.id] ? "0" : "1"}
          </button>
          <button type="button" onClick={() => dispatch({ type: "pulse", id: c.id })} title="Drive this input high then low: one clock pulse">
            Pulse
          </button>
          {c.clockHz !== undefined && (
            <label>
              Frequency
              <select value={c.clockHz} onChange={(e) => dispatch({ type: "setClockHz", id: c.id, hz: Number(e.target.value) })}>
                {[...new Set([...CLOCK_HZ_OPTIONS, c.clockHz])].sort((a, b) => a - b).map((hz) => (
                  <option key={hz} value={hz}>{hz} Hz</option>
                ))}
              </select>
            </label>
          )}
          <button
            type="button"
            aria-pressed={!!running[c.id]}
            className={running[c.id] ? "primary" : ""}
            onClick={() => onToggleRun(c.id)}
            title={c.clockHz !== undefined ? "Run this clock at its frequency" : "Toggle this input like a 1 Hz clock"}
          >
            {running[c.id] ? "Stop clock" : c.clockHz !== undefined ? "Run clock" : "Auto clock"}
          </button>
        </>
      )}
      <button type="button" className="danger" onClick={remove}>Delete {c.kind}</button>
    </div>
  );
}
