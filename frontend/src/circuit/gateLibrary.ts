import type { ComponentKind, EditorComponent, GateType } from "./circuitTypes";

export interface GateSpec {
  type: GateType;
  minInputs: number;
  maxInputs: number;
  defaultInputs: number;
  /** Used only by the live preview simulation. The backend is the source of truth for analysis. */
  simulate: (inputs: boolean[]) => boolean;
}

const parity = (v: boolean[]) => v.filter(Boolean).length % 2 === 1;

export const GATES: Record<GateType, GateSpec> = {
  AND: { type: "AND", minInputs: 2, maxInputs: 8, defaultInputs: 2, simulate: (v) => v.every(Boolean) },
  OR: { type: "OR", minInputs: 2, maxInputs: 8, defaultInputs: 2, simulate: (v) => v.some(Boolean) },
  NOT: { type: "NOT", minInputs: 1, maxInputs: 1, defaultInputs: 1, simulate: (v) => !v[0] },
  NAND: { type: "NAND", minInputs: 2, maxInputs: 8, defaultInputs: 2, simulate: (v) => !v.every(Boolean) },
  NOR: { type: "NOR", minInputs: 2, maxInputs: 8, defaultInputs: 2, simulate: (v) => !v.some(Boolean) },
  XOR: { type: "XOR", minInputs: 2, maxInputs: 8, defaultInputs: 2, simulate: parity },
  XNOR: { type: "XNOR", minInputs: 2, maxInputs: 8, defaultInputs: 2, simulate: (v) => !parity(v) },
  BUFFER: { type: "BUFFER", minInputs: 1, maxInputs: 1, defaultInputs: 1, simulate: (v) => v[0] },
};

export const GATE_ORDER: GateType[] = ["AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR", "BUFFER"];

// ---- Geometry ---------------------------------------------------------------------------

export const PIN_SPACING = 20;
export const GRID = 10;

export function componentSize(c: Pick<EditorComponent, "kind" | "pinCount">): { w: number; h: number } {
  if (c.kind === "gate") return { w: 70, h: Math.max(40, c.pinCount * PIN_SPACING + 10) };
  return { w: 64, h: 32 };
}

/** Position of input pin `pin` relative to the canvas. */
export function inputPinPosition(c: EditorComponent, pin: number): { x: number; y: number } {
  const { h } = componentSize(c);
  if (c.kind === "output") return { x: c.x, y: c.y + h / 2 };
  const span = (c.pinCount - 1) * PIN_SPACING;
  return { x: c.x, y: c.y + h / 2 - span / 2 + pin * PIN_SPACING };
}

export function outputPinPosition(c: EditorComponent): { x: number; y: number } {
  const { w, h } = componentSize(c);
  return { x: c.x + w, y: c.y + h / 2 };
}

export function hasOutputPin(kind: ComponentKind): boolean {
  return kind !== "output";
}

export const snap = (v: number) => Math.round(v / GRID) * GRID;
