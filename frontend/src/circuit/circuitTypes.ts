// ---- Editor model (UI state; never sent to the backend directly) ----------------------------

export type GateType =
  | "AND" | "OR" | "NOT" | "NAND" | "NOR" | "XOR" | "XNOR" | "BUFFER"
  | "MUX2" | "MUX4" | "DEMUX2" | "DEMUX4" | "DECODER2" | "DECODER3" | "ENCODER4" | "ENCODER8"
  | "VCC" | "GND" | "74138" | "74153" | "7476" | "7474";

export type ComponentKind = "input" | "gate" | "output";

export interface EditorComponent {
  id: string; // stable, never reused: input_1, gate_3, output_1 ...
  kind: ComponentKind;
  x: number;
  y: number;
  label?: string; // inputs and outputs
  gateType?: GateType; // gates
  /** Set on a clock source (an input that can be run as a square wave): its frequency in Hz. */
  clockHz?: number;
  pinCount: number; // number of input pins (0 for circuit inputs)
}

export interface Wire {
  id: string;
  from: string; // driving component id
  fromPin?: number; // which output pin of the driver (0 when omitted; only blocks have more than one)
  to: string; // sink component id
  pin: number; // input pin index on the sink
}

/** Contents of the flip-flops in the live preview. */
export interface SeqState {
  q: Record<string, boolean>; // stored bit of each flip-flop, keyed by `${icId}#ff${n}`
  clk: Record<string, boolean>; // clock level seen on each flip-flop at the last settle, for edge detection
}

export interface EditorState {
  components: EditorComponent[];
  wires: Wire[];
  inputValues: Record<string, boolean>; // live-simulation switch positions, keyed by input id
  counters: { input: number; gate: number; output: number; wire: number };
  seq?: SeqState; // present once the circuit contains flip-flops
}

// ---- Normalized circuit JSON (the API contract; see CIRCUIT_FORMAT.md) ----------------------

export interface NormalizedPosition {
  x: number;
  y: number;
}

export interface NormalizedCircuit {
  version: 1;
  inputs: { id: string; label: string; position?: NormalizedPosition }[];
  gates: { id: string; type: string; inputs: number; position?: NormalizedPosition }[];
  outputs: { id: string; label: string; position?: NormalizedPosition }[];
  connections: { from: string; to: string; input_index?: number; output_index?: number }[];
}
