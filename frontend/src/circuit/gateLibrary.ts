import type { EditorComponent, GateType } from "./circuitTypes";

export interface BlockInfo {
  /** Short title drawn on the block symbol, e.g. "MUX 4:1". */
  title: string;
  inputNames: string[];
  outputNames: string[];
  /** One-line description, used for integrated circuits. */
  description?: string;
}

/** Pin layout of a flip-flop IC; offsets are inside each flip-flop's block of input pins. */
export interface SequentialSpec {
  kind: "jk" | "d";
  ffs: number;
  stride: number;
  edge: "falling" | "rising";
  clk: number;
  pre: number; // active-low asynchronous preset
  clr: number; // active-low asynchronous clear (wins over preset)
  j?: number;
  k?: number;
  d?: number;
}

export interface GateSpec {
  type: GateType;
  minInputs: number;
  maxInputs: number;
  defaultInputs: number;
  /** Number of output pins: 1 for ordinary gates, more for DEMUX, decoders and encoders. */
  outputCount: number;
  /** Present for multi-pin blocks (MUX, DEMUX, decoder, encoder, ICs), absent for basic gates. */
  block?: BlockInfo;
  /** Flip-flop ICs: simulated per clock edge by the simulator, never by `simulate`. */
  sequential?: SequentialSpec;
  /** Constant sources (VCC/GND) are drawn with a dedicated symbol instead of a gate shape. */
  symbol?: "vcc" | "gnd";
  /** Used only by the live preview simulation. The backend is the source of truth for analysis. */
  simulate: (inputs: boolean[]) => boolean[];
}

const parity = (v: boolean[]) => v.filter(Boolean).length % 2 === 1;

/** Value of a bit vector read most-significant bit first. */
const bitsToNumber = (v: boolean[]) => v.reduce((n, bit) => (n << 1) | (bit ? 1 : 0), 0);

const gate = (type: GateType, minInputs: number, maxInputs: number, defaultInputs: number, fn: (v: boolean[]) => boolean): GateSpec => ({
  type,
  minInputs,
  maxInputs,
  defaultInputs,
  outputCount: 1,
  simulate: (v) => [fn(v)],
});

const names = (prefix: string, n: number) => Array.from({ length: n }, (_, i) => `${prefix}${i}`);
const selectNames = (n: number) => Array.from({ length: n }, (_, i) => `S${n - 1 - i}`);
const addressNames = (n: number) => Array.from({ length: n }, (_, i) => `A${n - 1 - i}`);

function block(type: GateType, title: string, inputNames: string[], outputNames: string[], simulate: (v: boolean[]) => boolean[], description?: string): GateSpec {
  return {
    type,
    minInputs: inputNames.length,
    maxInputs: inputNames.length,
    defaultInputs: inputNames.length,
    outputCount: outputNames.length,
    block: { title, inputNames, outputNames, description },
    simulate,
  };
}

const constant = (type: GateType, value: boolean, symbol: "vcc" | "gnd"): GateSpec => ({ ...gate(type, 0, 0, 0, () => value), symbol });

const flipFlopIc = (type: GateType, inputNames: string[], sequential: SequentialSpec, description: string): GateSpec => ({
  ...block(type, type, inputNames, ["1Q", "/1Q", "2Q", "/2Q"], () => [], description),
  sequential,
});

/** 74138 3-to-8 decoder. Pins: A, B, C, G1, /G2A, /G2B. Outputs are active low. */
const ic74138 = () =>
  block(
    "74138", "74138",
    ["A", "B", "C", "G1", "/G2A", "/G2B"],
    names("/Y", 8),
    (v) => {
      const [a, b, c, g1, g2a, g2b] = v;
      const enabled = g1 && !g2a && !g2b;
      const sel = bitsToNumber([c, b, a]);
      return Array.from({ length: 8 }, (_, k) => !(enabled && k === sel));
    },
    "3-to-8 decoder, active-low outputs",
  );

/** 74153 dual 4-to-1 multiplexer: shared selects A (LSB) and B, an active-low strobe per half. */
const ic74153 = () =>
  block(
    "74153", "74153",
    ["A", "B", "/1G", "1C0", "1C1", "1C2", "1C3", "/2G", "2C0", "2C1", "2C2", "2C3"],
    ["1Y", "2Y"],
    (v) => {
      const sel = bitsToNumber([v[1], v[0]]);
      return [2, 7].map((base) => !v[base] && v[base + 1 + sel]);
    },
    "Dual 4-to-1 multiplexer",
  );

const mux = (type: GateType, nData: number) =>
  block(type, `MUX ${nData}:1`, [...names("D", nData), ...selectNames(Math.log2(nData))], ["Y"], (v) => [v[bitsToNumber(v.slice(nData))]]);

const demux = (type: GateType, nOut: number) =>
  block(type, `DEMUX 1:${nOut}`, ["D", ...selectNames(Math.log2(nOut))], names("Y", nOut), (v) => {
    const sel = bitsToNumber(v.slice(1));
    return Array.from({ length: nOut }, (_, k) => v[0] && k === sel);
  });

const decoder = (type: GateType, nIn: number) =>
  block(type, `DEC ${nIn}:${2 ** nIn}`, addressNames(nIn), names("Y", 2 ** nIn), (v) => {
    const sel = bitsToNumber(v);
    return Array.from({ length: 2 ** nIn }, (_, k) => k === sel);
  });

/** Plain (non-priority) encoder: output bit b is the OR of every input whose index has bit b set. */
const encoder = (type: GateType, nIn: number) => {
  const nOut = Math.log2(nIn);
  return block(type, `ENC ${nIn}:${nOut}`, names("D", nIn), addressNames(nOut), (v) =>
    Array.from({ length: nOut }, (_, i) => {
      const bit = nOut - 1 - i; // most significant output first
      return v.some((on, k) => on && ((k >> bit) & 1) === 1);
    }),
  );
};

export const GATES: Record<GateType, GateSpec> = {
  AND: gate("AND", 2, 8, 2, (v) => v.every(Boolean)),
  OR: gate("OR", 2, 8, 2, (v) => v.some(Boolean)),
  NOT: gate("NOT", 1, 1, 1, (v) => !v[0]),
  NAND: gate("NAND", 2, 8, 2, (v) => !v.every(Boolean)),
  NOR: gate("NOR", 2, 8, 2, (v) => !v.some(Boolean)),
  XOR: gate("XOR", 2, 8, 2, parity),
  XNOR: gate("XNOR", 2, 8, 2, (v) => !parity(v)),
  BUFFER: gate("BUFFER", 1, 1, 1, (v) => v[0]),
  MUX2: mux("MUX2", 2),
  MUX4: mux("MUX4", 4),
  DEMUX2: demux("DEMUX2", 2),
  DEMUX4: demux("DEMUX4", 4),
  DECODER2: decoder("DECODER2", 2),
  DECODER3: decoder("DECODER3", 3),
  ENCODER4: encoder("ENCODER4", 4),
  ENCODER8: encoder("ENCODER8", 8),
  VCC: constant("VCC", true, "vcc"),
  GND: constant("GND", false, "gnd"),
  "74138": ic74138(),
  "74153": ic74153(),
  "7476": flipFlopIc(
    "7476",
    ["1CLK", "/1PRE", "/1CLR", "1J", "1K", "2CLK", "/2PRE", "/2CLR", "2J", "2K"],
    { kind: "jk", ffs: 2, stride: 5, edge: "falling", clk: 0, pre: 1, clr: 2, j: 3, k: 4 },
    "Dual JK flip-flop, falling-edge triggered",
  ),
  "7474": flipFlopIc(
    "7474",
    ["1D", "1CLK", "/1PRE", "/1CLR", "2D", "2CLK", "/2PRE", "/2CLR"],
    { kind: "d", ffs: 2, stride: 4, edge: "rising", clk: 1, pre: 2, clr: 3, d: 0 },
    "Dual D flip-flop, rising-edge triggered",
  ),
};

export const GATE_ORDER: GateType[] = ["AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR", "BUFFER"];
export const BLOCK_ORDER: GateType[] = ["MUX2", "MUX4", "DEMUX2", "DEMUX4", "DECODER2", "DECODER3", "ENCODER4", "ENCODER8"];

export const SOURCE_ORDER: GateType[] = ["VCC", "GND"];
/** Integrated circuits offered in the parts bin dropdown. */
export const IC_ORDER: GateType[] = ["74138", "74153", "7476", "7474"];

const isBlock = (type: GateType | undefined): boolean => !!type && !!GATES[type]?.block;

/** Text shown on a gate or block symbol and in the parts bin. */
export function gateLabel(type: GateType): string {
  return GATES[type].block?.title ?? (type === "BUFFER" ? "BUF" : type);
}

// ---- Geometry ---------------------------------------------------------------------------

const PIN_SPACING = 20;
const GRID = 10;

/** Number of output pins on a component (0 for circuit outputs). */
export function outputCount(c: Pick<EditorComponent, "kind" | "gateType">): number {
  if (c.kind === "output") return 0;
  if (c.kind === "gate" && c.gateType) return GATES[c.gateType]?.outputCount ?? 1;
  return 1;
}

/** Frequencies offered for a clock source, in Hz. They are slow on purpose: you watch the circuit count. */
export const CLOCK_HZ_OPTIONS = [0.5, 1, 2, 5, 10];
export const DEFAULT_CLOCK_HZ = 1;
export const clampClockHz = (hz: number): number => Math.min(20, Math.max(0.1, Number.isFinite(hz) ? hz : DEFAULT_CLOCK_HZ));
/** Time between the two edges of one clock period: half the period. */
export const clockHalfPeriodMs = (hz: number): number => 500 / clampClockHz(hz);

export function componentSize(c: Pick<EditorComponent, "kind" | "pinCount" | "gateType" | "clockHz">): { w: number; h: number } {
  if (c.kind === "input" && c.clockHz !== undefined) return { w: 80, h: 32 };
  if (c.kind === "gate") {
    if (c.gateType && GATES[c.gateType]?.symbol) return { w: 40, h: 40 };
    const pins = Math.max(c.pinCount, outputCount(c));
    return isBlock(c.gateType) ? { w: 96, h: pins * PIN_SPACING + 36 } : { w: 70, h: Math.max(40, pins * PIN_SPACING + 10) };
  }
  return { w: 64, h: 32 };
}

/** Position of input pin `pin` relative to the canvas. */
export function inputPinPosition(c: EditorComponent, pin: number): { x: number; y: number } {
  const { h } = componentSize(c);
  if (c.kind === "output") return { x: c.x, y: c.y + h / 2 };
  const span = (c.pinCount - 1) * PIN_SPACING;
  return { x: c.x, y: c.y + h / 2 - span / 2 + pin * PIN_SPACING };
}

export function outputPinPosition(c: EditorComponent, pin = 0): { x: number; y: number } {
  const { w, h } = componentSize(c);
  const span = (outputCount(c) - 1) * PIN_SPACING;
  return { x: c.x + w, y: c.y + h / 2 - span / 2 + pin * PIN_SPACING };
}

export const snap = (v: number) => Math.round(v / GRID) * GRID;
