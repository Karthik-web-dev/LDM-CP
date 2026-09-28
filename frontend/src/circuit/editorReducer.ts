import { GATES, snap } from "./gateLibrary";
import type { ComponentKind, EditorComponent, EditorState, GateType } from "./circuitTypes";

export type EditorAction =
  | { type: "add"; kind: ComponentKind; gateType?: GateType; x?: number; y?: number }
  | { type: "move"; id: string; x: number; y: number }
  | { type: "remove"; id: string }
  | { type: "connect"; from: string; to: string; pin: number }
  | { type: "removeWire"; id: string }
  | { type: "setLabel"; id: string; label: string }
  | { type: "setPinCount"; id: string; pinCount: number }
  | { type: "setGateType"; id: string; gateType: GateType }
  | { type: "toggleInput"; id: string }
  | { type: "scaffold"; inputs: string[]; outputs: string[] }
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

function makeComponent(state: EditorState, kind: ComponentKind, gateType?: GateType, x?: number, y?: number, label?: string): [EditorComponent, EditorState["counters"]] {
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
  else component.label = label ?? nextLabel(labels, kind);
  return [component, counters];
}

function withoutInvalidWires(state: EditorState): EditorState {
  const byId = new Map(state.components.map((c) => [c.id, c]));
  return {
    ...state,
    wires: state.wires.filter((w) => {
      const to = byId.get(w.to);
      return byId.has(w.from) && to !== undefined && w.pin < to.pinCount;
    }),
  };
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "add": {
      const [component, counters] = makeComponent(state, action.kind, action.gateType, action.x, action.y);
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
      if (!target || !source || source.kind === "output" || action.pin >= target.pinCount) return state;
      const counters = { ...state.counters, wire: state.counters.wire + 1 };
      // An input pin has a single driver: a new wire replaces the old one.
      const wires = state.wires.filter((w) => !(w.to === action.to && w.pin === action.pin));
      wires.push({ id: `wire_${counters.wire}`, from: action.from, to: action.to, pin: action.pin });
      return { ...state, wires, counters };
    }
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
      return { ...state, inputValues: { ...state.inputValues, [action.id]: !state.inputValues[action.id] } };
    case "scaffold": {
      let next = state;
      const have = (kind: ComponentKind, label: string) => next.components.some((c) => c.kind === kind && c.label === label);
      action.inputs.forEach((label, i) => {
        if (have("input", label)) return;
        const [c, counters] = makeComponent(next, "input", undefined, INPUT_X, 60 + i * 80, label);
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
