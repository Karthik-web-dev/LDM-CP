import { useState, type Dispatch, type DragEvent } from "react";
import type { EditorAction } from "../../circuit/editorReducer";
import type { ComponentKind, GateType } from "../../circuit/circuitTypes";
import { BLOCK_ORDER, GATES, GATE_ORDER, IC_ORDER, SOURCE_ORDER, gateLabel } from "../../circuit/gateLibrary";
import { GateShape } from "../CircuitEditor/CircuitEditor";
import "./PartsBin.css";

export const PART_MIME = "application/x-ldm-part";

export interface PartDrop {
  kind: ComponentKind;
  gateType?: GateType;
  clock?: boolean; // an input that runs as a clock source
}

interface Props {
  dispatch: Dispatch<EditorAction>;
}

/** Small bin icon: the real symbol for gates, a simplified box with evenly spaced pins for blocks. */
function PartIcon({ type }: { type: GateType }) {
  const spec = GATES[type];
  if (spec.symbol) {
    return (
      <svg viewBox="-2 -2 44 44" className="part-icon source" aria-hidden>
        <GateShape x={0} y={0} w={40} h={40} type={type} pins={0} showLabel={false} />
      </svg>
    );
  }
  if (spec.block) {
    const lead = (n: number, i: number) => 6 + ((i + 0.5) * 32) / n;
    return (
      <svg viewBox="0 0 64 44" className="part-icon block" aria-hidden>
        {Array.from({ length: spec.defaultInputs }, (_, i) => <line key={`i${i}`} x1="2" x2="14" y1={lead(spec.defaultInputs, i)} y2={lead(spec.defaultInputs, i)} className="lead" />)}
        {Array.from({ length: spec.outputCount }, (_, i) => <line key={`o${i}`} x1="50" x2="62" y1={lead(spec.outputCount, i)} y2={lead(spec.outputCount, i)} className="lead" />)}
        <rect x="14" y="3" width="36" height="38" className="gate-body" />
        <text x="32" y="26" className="block-title icon">{spec.block.title.split(" ")[0]}</text>
      </svg>
    );
  }
  return (
    <svg viewBox="-2 -2 74 44" className="part-icon" aria-hidden>
      <GateShape x={0} y={0} w={70} h={40} type={type} pins={spec.defaultInputs} showLabel={false} />
    </svg>
  );
}

export function PartsBin({ dispatch }: Props) {
  const [ic, setIc] = useState<GateType>(IC_ORDER[0]);
  const dragStart = (e: DragEvent, part: PartDrop) => {
    e.dataTransfer.setData(PART_MIME, JSON.stringify(part));
    e.dataTransfer.effectAllowed = "copy";
  };

  const gateButton = (type: GateType) => (
    <button
      key={type}
      type="button"
      className="part-btn"
      draggable
      onDragStart={(e) => dragStart(e, { kind: "gate", gateType: type })}
      onClick={() => dispatch({ type: "add", kind: "gate", gateType: type })}
      title={`${GATES[type].block ? gateLabel(type) : type}: drag onto the workspace, or click to add`}
    >
      <PartIcon type={type} />
      <span>{gateLabel(type)}</span>
    </button>
  );

  return (
    <aside className="parts-bin" aria-label="Parts bin">
      <div className="bin-title">Parts Bin</div>

      <details open className="bin-section">
        <summary>Sources &amp; Indicators</summary>
        <div className="bin-grid">
          <button
            type="button"
            className="part-btn"
            draggable
            onDragStart={(e) => dragStart(e, { kind: "input" })}
            onClick={() => dispatch({ type: "add", kind: "input" })}
            title="Input switch: drag onto the workspace, or click to add"
          >
            <svg viewBox="0 0 40 24" className="part-icon" aria-hidden>
              <rect x="2" y="3" width="26" height="18" className="gate-body" />
              <rect x="6" y="7" width="12" height="10" className="switch-knob" />
              <path d="M28 12h10" className="lead" />
            </svg>
            <span>Switch</span>
          </button>
          <button
            type="button"
            className="part-btn"
            draggable
            onDragStart={(e) => dragStart(e, { kind: "output" })}
            onClick={() => dispatch({ type: "add", kind: "output" })}
            title="Output lamp: drag onto the workspace, or click to add"
          >
            <svg viewBox="0 0 40 24" className="part-icon" aria-hidden>
              <path d="M2 12h10" className="lead" />
              <circle cx="24" cy="12" r="9" className="gate-body" />
              <path d="M18 6l12 12M30 6L18 18" className="lead" />
            </svg>
            <span>Lamp</span>
          </button>
          {SOURCE_ORDER.map(gateButton)}
          <button
            type="button"
            className="part-btn"
            draggable
            onDragStart={(e) => dragStart(e, { kind: "input", clock: true })}
            onClick={() => dispatch({ type: "add", kind: "input", clock: true })}
            title="Clock source with an adjustable frequency: drag onto the workspace, or click to add"
          >
            <svg viewBox="0 0 40 24" className="part-icon" aria-hidden>
              <rect x="2" y="3" width="26" height="18" className="gate-body" />
              <path d="M6 16V8H11V16H16V8H21V16H24" className="clock-wave" />
              <path d="M28 12h10" className="lead" />
            </svg>
            <span>Clock</span>
          </button>
        </div>
      </details>

      <details open className="bin-section">
        <summary>74xx ICs</summary>
        <div className="ic-picker">
          <select aria-label="IC type" value={ic} onChange={(e) => setIc(e.target.value as GateType)}>
            {IC_ORDER.map((t) => (
              <option key={t} value={t}>{gateLabel(t)}: {GATES[t].block?.description}</option>
            ))}
          </select>
          {gateButton(ic)}
          <p className="muted small">{GATES[ic].block?.description}. Drag it out, or click to add.</p>
        </div>
      </details>

      <details open className="bin-section">
        <summary>Logic Gates</summary>
        <div className="bin-grid">{GATE_ORDER.map(gateButton)}</div>
      </details>

      <details open className="bin-section">
        <summary>Combinational Blocks</summary>
        <div className="bin-grid">{BLOCK_ORDER.map(gateButton)}</div>
      </details>
    </aside>
  );
}
