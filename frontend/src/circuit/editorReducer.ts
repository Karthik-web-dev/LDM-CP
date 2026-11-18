import { DEFAULT_CLOCK_HZ, GATES, clampClockHz, outputCount, snap } from "./gateLibrary";
import { hasSequential, settle } from "./simulator";
import type { ComponentKind, EditorComponent, EditorState, GateType } from "./circuitTypes";

export type EditorAction =
  | { type: "add"; kind: ComponentKind; gateType?: GateType; clock?: boolean; x?: number; y?: number }
  | { type: "setClockHz"; id: string; hz: number }
  | { type: "move"; id: string; x: number; y: number }
  | { type: "remove"; id: string }
  | { type: "connect"; from: string; fromPin?: number; to: string; pin: number }
  | { type: "removeWire"; id: string }
  | { type: "setLabel"; id: string; label: string }
  | { type: "setPinCount"; id: string; pinCount: number }
  | { type: "setGateType"; id: string; gateType: GateType }
  | { type: "toggleInput"; id: string }
  | { type: "pulse"; id: string } // drive an input high, then low: one full clock pulse
  | { type: "resetSequential" } // set every flip-flop to 0 (then apply /PRE and /CLR)
  | { type: "scaffold"; inputs: string[]; outputs: string[]; clock?: string } // `clock`: the input label that is a clock source
  | { type: "clear" }
  | { type: "load"; state: EditorState };

export const emptyEditorState = (): EditorState => ({
  components: [],
  wires: [],
  inputValues: {},
  counters: { input: 0, gate: 0, output: 0, wire: 0 },
});

const INPUT_X = 40;
const OUTPUT_X = 540;

function nextLabel(existing: Set<string>, kind: "input" | "output"): string {
  if (kind === "input") {
    for (const ch of "ABCDEFGHIJKLMNOPQRSTUVWXZ") if (!existing.has(ch)) return ch;
  }
  for (let i = 1; ; i++) {
    const label = i === 1 ? "Y" : `Y${i}`;
    if (!existing.has(label)) return label;
  }
}

function clockLabel(existing: Set<string>): string {
  for (let i = 1; ; i++) {
    const label = i === 1 ? "CLK" : `CLK${i}`;
    if (!existing.has(label)) return label;
  }
}

function makeComponent(state: EditorState, kind: ComponentKind, gateType?: GateType, x?: number, y?: number, label?: string, clock?: boolean): [EditorComponent, EditorState["counters"]] {
  const counters = { ...state.counters, [kind]: state.counters[kind] + 1 };
  const id = `${kind}_${counters[kind]}`;
  const sameKind = state.components.filter((c) => c.kind === kind);
  const labels = new Set(sameKind.map((c) => c.label ?? ""));
  const defaultY = 40 + sameKind.length * (kind === "gate" ? 30 : 70);
  const component: EditorComponent = {
    id,
    kind,
    x: snap(x ?? (kind === "input" ? INPUT_X : kind === "output" ? OUTPUT_X : 200 + (sameKind.length % 3) * 100)),
    y: snap(y ?? (kind === "gate" ? 60 + (sameKind.length % 6) * 70 : defaultY)),
    pinCount: kind === "gate" ? GATES[gateType ?? "AND"].defaultInputs : kind === "output" ? 1 : 0,
  };
  if (kind === "gate") component.gateType = gateType ?? "AND";
  else component.label = label ?? (clock && kind === "input" ? clockLabel(labels) : nextLabel(labels, kind));
  if (clock && kind === "input") component.clockHz = DEFAULT_CLOCK_HZ;
  return [component, counters];
}

function withoutInvalidWires(state: EditorState): EditorState {
  const byId = new Map(state.components.map((c) => [c.id, c]));
  return {
    ...state,
    wires: state.wires.filter((w) => {
      const from = byId.get(w.from);
      const to = byId.get(w.to);
      return (
        from !== undefined &&
        to !== undefined &&
        w.pin < to.pinCount &&
        (w.fromPin ?? 0) < Math.max(outputCount(from), 1)
      );
    }),
  };
}

/** Edits that can change what the flip-flops see; they never count as a clock edge. */
const STRUCTURAL = new Set<EditorAction["type"]>(["add", "remove", "connect", "removeWire", "setPinCount", "setGateType", "scaffold", "load"]);

function withSeq(state: EditorState, applyEdges: boolean): EditorState {
  return hasSequential(state) ? { ...state, seq: settle(state, applyEdges) } : state;
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "toggleInput":
      return withSeq({ ...state, inputValues: { ...state.inputValues, [action.id]: !state.inputValues[action.id] } }, true);
    case "pulse": {
      const high = withSeq({ ...state, inputValues: { ...state.inputValues, [action.id]: true } }, true);
      return withSeq({ ...high, inputValues: { ...high.inputValues, [action.id]: false } }, true);
    }
    case "resetSequential":
      return withSeq({ ...state, seq: undefined }, false);
    default: {
      const next = reduceBase(state, action);
      return STRUCTURAL.has(action.type) ? withSeq(next, false) : next;
    }
  }
}

function reduceBase(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "add": {
      const [component, counters] = makeComponent(state, action.kind, action.gateType, action.x, action.y, undefined, action.clock);
      return { ...state, components: [...state.components, component], counters };
    }
    case "move":
      return {
        ...state,
        components: state.components.map((c) => (c.id === action.id ? { ...c, x: snap(action.x), y: snap(action.y) } : c)),
      };
    case "remove": {
      const inputValues = { ...state.inputValues };
      delete inputValues[action.id];
      return withoutInvalidWires({ ...state, inputValues, components: state.components.filter((c) => c.id !== action.id) });
    }
    case "connect": {
      const target = state.components.find((c) => c.id === action.to);
      const source = state.components.find((c) => c.id === action.from);
      const fromPin = action.fromPin ?? 0;
      if (!target || !source || source.kind === "output" || action.pin >= target.pinCount || fromPin >= outputCount(source)) return state;
      const counters = { ...state.counters, wire: state.counters.wire + 1 };
      // An input pin has a single driver: a new wire replaces the old one.
      const wires = state.wires.filter((w) => !(w.to === action.to && w.pin === action.pin));
      wires.push({ id: `wire_${counters.wire}`, from: action.from, ...(fromPin ? { fromPin } : {}), to: action.to, pin: action.pin });
      return { ...state, wires, counters };
    }
    case "setClockHz":
      return {
        ...state,
        components: state.components.map((c) => (c.id === action.id && c.clockHz !== undefined ? { ...c, clockHz: clampClockHz(action.hz) } : c)),
      };
    case "removeWire":
      return { ...state, wires: state.wires.filter((w) => w.id !== action.id) };
    case "setLabel":
      return { ...state, components: state.components.map((c) => (c.id === action.id ? { ...c, label: action.label } : c)) };
    case "setPinCount":
      return withoutInvalidWires({
        ...state,
        components: state.components.map((c) => (c.id === action.id ? { ...c, pinCount: action.pinCount } : c)),
      });
    case "setGateType": {
      const spec = GATES[action.gateType];
      return withoutInvalidWires({
        ...state,
        components: state.components.map((c) =>
          c.id === action.id
            ? { ...c, gateType: action.gateType, pinCount: Math.min(spec.maxInputs, Math.max(spec.minInputs, c.pinCount)) }
            : c,
        ),
      });
    }
    case "toggleInput":
    case "pulse":
    case "resetSequential":
      return state; // handled in editorReducer
    case "scaffold": {
      let next = state;
      const have = (kind: ComponentKind, label: string) => next.components.some((c) => c.kind === kind && c.label === label);
      action.inputs.forEach((label, i) => {
        if (have("input", label)) return;
        const [c, counters] = makeComponent(next, "input", undefined, INPUT_X, 60 + i * 80, label, label === action.clock);
        next = { ...next, components: [...next.components, c], counters };
      });
      action.outputs.forEach((label, i) => {
        if (have("output", label)) return;
        const [c, counters] = makeComponent(next, "output", undefined, OUTPUT_X, 100 + i * 120, label);
        next = { ...next, components: [...next.components, c], counters };
      });
      return next;
    }
    case "clear":
      return emptyEditorState();
    case "load":
      return action.state;
  }
}
