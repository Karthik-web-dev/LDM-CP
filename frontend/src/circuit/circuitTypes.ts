// ---- Editor model (UI state; never sent to the backend directly) ----------------------------

export type GateType = "AND" | "OR" | "NOT" | "NAND" | "NOR" | "XOR" | "XNOR" | "BUFFER";

export type ComponentKind = "input" | "gate" | "output";

export interface EditorComponent {
  id: string; // stable, never reused: input_1, gate_3, output_1 ...
  kind: ComponentKind;
  x: number;
  y: number;
  label?: string; // inputs and outputs
  gateType?: GateType; // gates
  pinCount: number; // number of input pins (0 for circuit inputs)
}

export interface Wire {
  id: string;
  from: string; // driving component id
  to: string; // sink component id
  pin: number; // input pin index on the sink
}

export interface EditorState {
  components: EditorComponent[];
  wires: Wire[];
  inputValues: Record<string, boolean>; // live-simulation switch positions, keyed by input id
  counters: { input: number; gate: number; output: number; wire: number };
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
  connections: { from: string; to: string; input_index?: number }[];
}
