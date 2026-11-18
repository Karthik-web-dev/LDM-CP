import { useMemo, useRef, useState, type Dispatch, type DragEvent, type PointerEvent as ReactPointerEvent } from "react";
import type { EditorAction } from "../../circuit/editorReducer";
import type { ComponentKind, EditorComponent, EditorState, GateType, Wire } from "../../circuit/circuitTypes";
import { GATES, componentSize, gateLabel, inputPinPosition, outputCount, outputPinPosition } from "../../circuit/gateLibrary";
import { signalKey, type SignalMap } from "../../circuit/simulator";
import { PART_MIME, type PartDrop } from "../PartsBin/PartsBin";
import "./CircuitEditor.css";

export type Selection = { kind: "component" | "wire"; id: string } | null;

interface Props {
  state: EditorState;
  dispatch: Dispatch<EditorAction>;
  signals: SignalMap;
  selection: Selection;
  onSelect: (s: Selection) => void;
  errorIds: Set<string>;
  focusIds: Set<string>;
  /** Clock sources (by id) that are currently running, to mark them on the canvas. */
  running?: Record<string, boolean>;
}

type PortRef = { comp: string; dir: "in" | "out"; pin: number };
type Drag =
  | { mode: "move"; id: string; dx: number; dy: number; startX: number; startY: number; moved: boolean }
  | { mode: "wire"; port: PortRef; x0: number; y0: number; x: number; y: number };

const MIN_W = 680;
const MIN_H = 440;

export function CircuitEditor({ state, dispatch, signals, selection, onSelect, errorIds, focusIds, running = {} }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const byId = useMemo(() => new Map(state.components.map((c) => [c.id, c])), [state.components]);

  const width = Math.max(MIN_W, ...state.components.map((c) => c.x + componentSize(c).w + 80));
  const height = Math.max(MIN_H, ...state.components.map((c) => c.y + componentSize(c).h + 60));

  const toSvg = (e: { clientX: number; clientY: number }) => {
    const svg = svgRef.current!;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM()!.inverse());
    return { x: pt.x, y: pt.y };
  };

  const startMove = (e: ReactPointerEvent, c: EditorComponent) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const p = toSvg(e);
    svgRef.current?.setPointerCapture(e.pointerId);
    setDrag({ mode: "move", id: c.id, dx: p.x - c.x, dy: p.y - c.y, startX: p.x, startY: p.y, moved: false });
  };

  const startWire = (e: ReactPointerEvent, port: PortRef) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const c = byId.get(port.comp)!;
    const at = port.dir === "out" ? outputPinPosition(c, port.pin) : inputPinPosition(c, port.pin);
    svgRef.current?.setPointerCapture(e.pointerId);
    setDrag({ mode: "wire", port, x0: at.x, y0: at.y, x: at.x, y: at.y });
  };

  const onPointerMove = (e: ReactPointerEvent) => {
    if (!drag) return;
    const p = toSvg(e);
    if (drag.mode === "move") {
      const moved = drag.moved || Math.hypot(p.x - drag.startX, p.y - drag.startY) > 3;
      if (moved) dispatch({ type: "move", id: drag.id, x: Math.max(0, p.x - drag.dx), y: Math.max(0, p.y - drag.dy) });
      if (moved !== drag.moved) setDrag({ ...drag, moved });
    } else {
      setDrag({ ...drag, x: p.x, y: p.y });
    }
  };

  const onPointerUp = (e: ReactPointerEvent) => {
    if (!drag) return;
    svgRef.current?.releasePointerCapture(e.pointerId);
    if (drag.mode === "move") {
      if (!drag.moved) {
        const c = byId.get(drag.id);
        if (c?.kind === "input") dispatch({ type: "toggleInput", id: c.id });
        onSelect({ kind: "component", id: drag.id });
      }
    } else {
      const el = document.elementFromPoint(e.clientX, e.clientY)?.closest<SVGElement>("[data-port]");
      if (el) {
        const end: PortRef = { comp: el.dataset.comp!, dir: el.dataset.port as "in" | "out", pin: Number(el.dataset.pin ?? 0) };
        const [src, dst] = drag.port.dir === "out" ? [drag.port, end] : [end, drag.port];
        if (src.dir === "out" && dst.dir === "in") dispatch({ type: "connect", from: src.comp, fromPin: src.pin, to: dst.comp, pin: dst.pin });
      }
    }
    setDrag(null);
  };

  /** A part dragged out of the parts bin and dropped on the canvas. */
  const onDrop = (e: DragEvent) => {
    const raw = e.dataTransfer.getData(PART_MIME);
    if (!raw) return;
    e.preventDefault();
    try {
      const part = JSON.parse(raw) as PartDrop;
      const p = toSvg(e);
      const kind: ComponentKind = part.kind;
      const size = componentSize({ kind, pinCount: 0, gateType: part.gateType, clockHz: part.clock ? 1 : undefined });
      dispatch({ type: "add", kind, gateType: part.gateType as GateType | undefined, clock: part.clock, x: Math.max(0, p.x - size.w / 2), y: Math.max(0, p.y - size.h / 2) });
    } catch {
      /* not one of our parts */
    }
  };

  const wirePath = (x1: number, y1: number, x2: number, y2: number) => {
    const dx = Math.max(30, Math.abs(x2 - x1) / 2);
    return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
  };

  const renderWire = (w: Wire) => {
    const from = byId.get(w.from);
    const to = byId.get(w.to);
    if (!from || !to) return null;
    const a = outputPinPosition(from, w.fromPin ?? 0);
    const b = inputPinPosition(to, w.pin);
    const d = wirePath(a.x, a.y, b.x, b.y);
    const v = signals.get(signalKey(w.from, w.fromPin ?? 0));
    const selected = selection?.kind === "wire" && selection.id === w.id;
    return (
      <g key={w.id} className="wire-group" onPointerDown={(e) => { e.stopPropagation(); onSelect({ kind: "wire", id: w.id }); }}>
        <path d={d} className="wire-hit" />
        <path d={d} className={`wire ${v === true ? "on" : v === false ? "off" : "unknown"} ${selected ? "selected" : ""}`} />
      </g>
    );
  };

  const port = (c: EditorComponent, dir: "in" | "out", pin: number) => {
    const p = dir === "out" ? outputPinPosition(c, pin) : inputPinPosition(c, pin);
    return (
      <g key={`${dir}${pin}`} className="port" data-port={dir} data-comp={c.id} data-pin={pin} onPointerDown={(e) => startWire(e, { comp: c.id, dir, pin })}>
        <circle cx={p.x} cy={p.y} r={11} className="port-hit" />
        <circle cx={p.x} cy={p.y} r={4.5} className="port-dot" />
      </g>
    );
  };

  const renderComponent = (c: EditorComponent) => {
    const { w, h } = componentSize(c);
    const v = signals.get(c.id);
    const classes = [
      "component",
      c.kind,
      selection?.kind === "component" && selection.id === c.id ? "selected" : "",
      errorIds.has(c.id) ? "has-error" : "",
      focusIds.has(c.id) ? "focused" : "",
    ].join(" ");
    return (
      <g key={c.id} className={classes}>
        <g onPointerDown={(e) => startMove(e, c)} className="component-body">
          <text x={c.x} y={c.y - 6} className="component-id">{c.id}</text>
          {c.kind === "gate" && <GateShape x={c.x} y={c.y} w={w} h={h} type={c.gateType!} pins={c.pinCount} />}
          {c.kind === "input" && c.clockHz !== undefined && (
            <>
              <rect x={c.x} y={c.y} width={w} height={h} rx={2} className="io-box" />
              <path
                d={`M ${c.x + 6} ${c.y + 22} V ${c.y + 10} H ${c.x + 14} V ${c.y + 22} H ${c.x + 22} V ${c.y + 10} H ${c.x + 30}`}
                className={`clock-wave ${v ? "on" : ""}`}
              />
              <text x={c.x + 36} y={c.y + 21} className="io-label">{c.label}</text>
              <text x={c.x} y={c.y + h + 11} className="clock-hz">{c.clockHz} Hz{running[c.id] ? " ▶ running" : ""}</text>
            </>
          )}
          {c.kind === "input" && c.clockHz === undefined && (
            <>
              <rect x={c.x} y={c.y} width={w} height={h} rx={2} className="io-box" />
              <rect x={c.x + 6} y={c.y + 8} width={22} height={16} rx={2} className={`switch ${v ? "on" : ""}`} />
              <rect x={v ? c.x + 17 : c.x + 8} y={c.y + 10} width={9} height={12} className="switch-knob" />
              <text x={c.x + 44} y={c.y + 21} className="io-label">{c.label}</text>
            </>
          )}
          {c.kind === "output" && (
            <>
              <rect x={c.x} y={c.y} width={w} height={h} rx={2} className="io-box" />
              <circle cx={c.x + 18} cy={c.y + 16} r={8} className={`lamp ${v === true ? "on" : v === false ? "off" : "unknown"}`} />
              <text x={c.x + 44} y={c.y + 21} className="io-label">{c.label}</text>
            </>
          )}
        </g>
        {Array.from({ length: c.pinCount }, (_, i) => port(c, "in", i))}
        {Array.from({ length: outputCount(c) }, (_, i) => port(c, "out", i))}
      </g>
    );
  };

  return (
    <div className="editor-scroll">
      <svg
        ref={svgRef}
        className="editor-canvas"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerDown={() => onSelect(null)}
        onDragOver={(e) => { if (e.dataTransfer.types.includes(PART_MIME)) e.preventDefault(); }}
        onDrop={onDrop}
        role="application"
        aria-label="Circuit editor canvas"
      >
        <defs>
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="1" className="grid-dot" />
          </pattern>
        </defs>
        <rect width={width} height={height} fill="url(#grid)" />
        {state.components.length === 0 && (
          <text x={width / 2} y={height / 2} className="empty-hint">
            Drag parts from the bin onto the workspace, then drag between pins to wire them.
          </text>
        )}
        <g>{state.wires.map(renderWire)}</g>
        {drag?.mode === "wire" && <path d={wirePath(drag.x0, drag.y0, drag.x, drag.y)} className="wire pending" />}
        <g>{state.components.map(renderComponent)}</g>
      </svg>
    </div>
  );
}

export function GateShape({ x, y, w, h, type, pins, showLabel = true }: { x: number; y: number; w: number; h: number; type: GateType; pins: number; showLabel?: boolean }) {
  const spec = GATES[type];
  if (spec.symbol) return <SourceShape x={x} y={y} w={w} h={h} kind={spec.symbol} />;
  if (spec.block) return <BlockShape x={x} y={y} w={w} h={h} type={type} detail={showLabel} />;

  const bubble = type === "NOT" || type === "NAND" || type === "NOR" || type === "XNOR";
  const left = x + 12;
  const right = x + w - (bubble ? 20 : 12);
  const top = y + 4;
  const bottom = y + h - 4;
  const mid = y + h / 2;
  const r = (bottom - top) / 2;

  let body: string;
  if (type === "AND" || type === "NAND") {
    body = `M ${left} ${top} H ${right - r} A ${r} ${r} 0 0 1 ${right - r} ${bottom} H ${left} Z`;
  } else if (type === "OR" || type === "NOR" || type === "XOR" || type === "XNOR") {
    body = `M ${left} ${top} Q ${left + 14} ${mid} ${left} ${bottom} Q ${right - 12} ${bottom} ${right} ${mid} Q ${right - 12} ${top} ${left} ${top} Z`;
  } else {
    body = `M ${left} ${top} L ${right} ${mid} L ${left} ${bottom} Z`;
  }
  const span = (pins - 1) * 20;
  return (
    <g className="gate-shape">
      {Array.from({ length: pins }, (_, i) => {
        const py = mid - span / 2 + i * 20;
        return <line key={i} x1={x} y1={py} x2={left + 8} y2={py} className="lead" />;
      })}
      <line x1={bubble ? right + 8 : right} y1={mid} x2={x + w} y2={mid} className="lead" />
      {(type === "XOR" || type === "XNOR") && <path d={`M ${left - 6} ${top} Q ${left + 8} ${mid} ${left - 6} ${bottom}`} className="gate-extra" />}
      <path d={body} className="gate-body" />
      {bubble && <circle cx={right + 4} cy={mid} r={4} className="gate-body" />}
      {showLabel && (
        <text x={(left + right) / 2 - (type === "NOT" || type === "BUFFER" ? 6 : 0)} y={mid + 4} className="gate-label">{gateLabel(type)}</text>
      )}
    </g>
  );
}

/** Constant source symbol: a supply rail for VCC, a ground symbol for GND, with a lead to the output pin. */
function SourceShape({ x, y, w, h, kind }: { x: number; y: number; w: number; h: number; kind: "vcc" | "gnd" }) {
  const mid = y + h / 2;
  return (
    <g className="gate-shape source-shape">
      {kind === "vcc" ? (
        <>
          <line x1={x + 14} y1={y + 8} x2={x + 14} y2={y + h - 8} className="lead rail" />
          <line x1={x + 14} y1={mid} x2={x + w} y2={mid} className="lead" />
        </>
      ) : (
        <>
          <line x1={x + 8} y1={y + 6} x2={x + 8} y2={y + h - 6} className="lead rail" />
          <line x1={x + 13} y1={y + 12} x2={x + 13} y2={y + h - 12} className="lead rail" />
          <line x1={x + 18} y1={y + 17} x2={x + 18} y2={y + h - 17} className="lead rail" />
          <line x1={x + 18} y1={mid} x2={x + w} y2={mid} className="lead" />
        </>
      )}
      <text x={x + w / 2 + 2} y={mid - 6} className="gate-label">{kind === "vcc" ? "VCC" : "GND"}</text>
    </g>
  );
}

/** Rectangular symbol for MUX / DEMUX / decoder / encoder, with a label next to every pin. */
function BlockShape({ x, y, w, h, type, detail }: { x: number; y: number; w: number; h: number; type: GateType; detail: boolean }) {
  const { block } = GATES[type];
  if (!block) return null;
  const mid = y + h / 2;
  const pinY = (i: number, n: number) => mid - ((n - 1) * 20) / 2 + i * 20;
  const left = x + 12;
  const right = x + w - 12;
  return (
    <g className="gate-shape block-shape">
      {block.inputNames.map((_, i) => (
        <line key={`i${i}`} x1={x} y1={pinY(i, block.inputNames.length)} x2={left} y2={pinY(i, block.inputNames.length)} className="lead" />
      ))}
      {block.outputNames.map((_, i) => (
        <line key={`o${i}`} x1={right} y1={pinY(i, block.outputNames.length)} x2={x + w} y2={pinY(i, block.outputNames.length)} className="lead" />
      ))}
      <rect x={left} y={y + 4} width={right - left} height={h - 8} className="gate-body" />
      {detail ? (
        <>
          <text x={(left + right) / 2} y={y + 17} className="block-title">{block.title}</text>
          {block.inputNames.map((n, i) => (
            <text key={`ti${i}`} x={left + 4} y={pinY(i, block.inputNames.length) + 3} className="pin-label">{n}</text>
          ))}
          {block.outputNames.map((n, i) => (
            <text key={`to${i}`} x={right - 4} y={pinY(i, block.outputNames.length) + 3} className="pin-label end">{n}</text>
          ))}
        </>
      ) : (
        <text x={(left + right) / 2} y={mid + 3} className="block-title icon">{block.title.split(" ")[0]}</text>
      )}
    </g>
  );
}
