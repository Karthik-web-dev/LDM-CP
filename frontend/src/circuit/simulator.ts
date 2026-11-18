import { GATES, outputCount } from "./gateLibrary";
import type { EditorComponent, EditorState, SeqState } from "./circuitTypes";

/**
 * Signal value on a component's output pin: true/false, or undefined when it cannot be determined.
 * Keyed by `signalKey`: output pin 0 uses the plain component id, further pins use `id#pin`.
 */
export type SignalMap = Map<string, boolean | undefined>;

export const signalKey = (id: string, pin = 0): string => (pin === 0 ? id : `${id}#${pin}`);

/** Key of one flip-flop inside a flip-flop IC, used in `SeqState`. */
const ffKey = (id: string, ff: number): string => `${id}#ff${ff}`;

/** Key of the remembered output of a gate that is part of a feedback loop (a latch). */
const loopKey = (id: string, pin: number): string => `${id}#loop${pin}`;

const isSequential = (c: EditorComponent): boolean => c.kind === "gate" && !!c.gateType && !!GATES[c.gateType]?.sequential;

/**
 * Ids of the plain gates that sit on a feedback loop, such as two cross-coupled NAND gates. They
 * remember their output between input changes, so they are simulated from a stored value, not from
 * "unknown". A flip-flop breaks a loop (it has its own stored bit).
 */
function feedbackGateIds(state: EditorState): Set<string> {
  const byId = new Map(state.components.map((c) => [c.id, c]));
  const next = new Map<string, string[]>();
  for (const w of state.wires) {
    const target = byId.get(w.to);
    if (!target || isSequential(target)) continue;
    next.set(w.from, [...(next.get(w.from) ?? []), w.to]);
  }
  const loops = new Set<string>();
  for (const c of state.components) {
    if (c.kind !== "gate" || isSequential(c)) continue;
    const seen = new Set<string>();
    const stack = [...(next.get(c.id) ?? [])];
    while (stack.length) {
      const id = stack.pop()!;
      if (id === c.id) {
        loops.add(c.id);
        break;
      }
      if (!seen.has(id)) {
        seen.add(id);
        stack.push(...(next.get(id) ?? []));
      }
    }
  }
  return loops;
}

/** The circuit has memory: flip-flops, or gates wired in a feedback loop. */
export const hasSequential = (state: EditorState): boolean => state.components.some(isSequential) || feedbackGateIds(state).size > 0;

interface Propagation {
  values: SignalMap;
  /** Value on input pin `pin` of component `id`, or undefined when unwired or not yet known. */
  readPin: (id: string, pin: number) => boolean | undefined;
  /** Gates on a feedback loop. */
  loops: Set<string>;
}

/**
 * Combinational propagation for the current switch positions, with flip-flop outputs and loop gates
 * held at their stored values in `q`. Values propagate by repeated relaxation in component order, so
 * an unfinished or oscillating circuit stops after a bounded number of passes instead of hanging.
 */
function propagate(state: EditorState, q: Record<string, boolean>): Propagation {
  const values: SignalMap = new Map();
  const drivers = new Map<string, Map<number, string[]>>();
  for (const w of state.wires) {
    const pins = drivers.get(w.to) ?? new Map<number, string[]>();
    pins.set(w.pin, [...(pins.get(w.pin) ?? []), signalKey(w.from, w.fromPin ?? 0)]);
    drivers.set(w.to, pins);
  }

  const readPin = (id: string, pin: number): boolean | undefined => {
    const sources = drivers.get(id)?.get(pin) ?? [];
    return sources.length === 1 ? values.get(sources[0]) : undefined;
  };

  const loops = feedbackGateIds(state);
  for (const c of state.components) {
    if (c.kind === "input") values.set(c.id, state.inputValues[c.id] ?? false);
    if (isSequential(c)) {
      // A flip-flop IC's outputs are its stored bits: Q, then /Q, for each flip-flop.
      for (let f = 0; f < GATES[c.gateType!].sequential!.ffs; f++) {
        const bit = q[ffKey(c.id, f)] ?? false;
        values.set(signalKey(c.id, 2 * f), bit);
        values.set(signalKey(c.id, 2 * f + 1), !bit);
      }
    } else if (loops.has(c.id)) {
      for (let k = 0; k < outputCount(c); k++) values.set(signalKey(c.id, k), q[loopKey(c.id, k)] ?? false);
    }
  }

  for (let pass = 0; pass <= state.components.length; pass++) {
    let changed = false;
    const set = (key: string, value: boolean | undefined) => {
      if (values.get(key) !== value) {
        values.set(key, value);
        changed = true;
      }
    };
    for (const c of state.components) {
      if (c.kind === "input" || isSequential(c)) continue;
      if (c.kind === "output") {
        set(c.id, readPin(c.id, 0));
        continue;
      }
      const spec = c.gateType ? GATES[c.gateType] : undefined;
      const ins = Array.from({ length: c.pinCount }, (_, i) => readPin(c.id, i));
      const known = spec !== undefined && ins.every((v) => v !== undefined);
      const outs = known ? spec.simulate(ins as boolean[]) : [];
      for (let k = 0; k < (spec?.outputCount ?? 1); k++) set(signalKey(c.id, k), known ? outs[k] : undefined);
    }
    if (!changed) break;
  }
  return { values, readPin, loops };
}

/**
 * Live preview simulation for the editor: which wires and lamps are lit for the current switch
 * positions and stored values. This is interaction feedback only. Boolean expressions, truth tables,
 * sequence checks and correctness always come from the backend.
 */
export function simulate(state: EditorState): SignalMap {
  return propagate(state, state.seq?.q ?? {}).values;
}

const MAX_PASSES = 200;

/**
 * Let the memory elements react to the current switch positions and return their new stored values.
 *
 * With `applyEdges`, a flip-flop whose clock pin made its active transition since the last pass
 * samples its data pins (all flip-flops sample simultaneously, from the values before the edge).
 * A change in one flip-flop can clock another, so this repeats until nothing changes, which is how
 * a ripple counter works. Without `applyEdges`, clock levels are only recorded (used after wiring
 * changes so editing never counts as a clock pulse). Active-low /PRE and /CLR always apply, and
 * /CLR wins over /PRE. Unwired flip-flop pins read as high, like unconnected TTL inputs. Gates in a
 * feedback loop keep their output from the previous settle, which is what makes a latch hold.
 */
export function settle(state: EditorState, applyEdges: boolean): SeqState {
  const ics = state.components.filter(isSequential);
  const q: Record<string, boolean> = { ...(state.seq?.q ?? {}) };
  let clk: Record<string, boolean> = { ...(state.seq?.clk ?? {}) };
  for (const c of ics) {
    for (let f = 0; f < GATES[c.gateType!].sequential!.ffs; f++) q[ffKey(c.id, f)] ??= false;
  }

  for (let pass = 0; pass < MAX_PASSES; pass++) {
    const { values, readPin, loops } = propagate(state, q);
    for (const id of loops) {
      const gate = state.components.find((c) => c.id === id)!;
      for (let k = 0; k < outputCount(gate); k++) q[loopKey(id, k)] = values.get(signalKey(id, k)) ?? false;
    }
    const nextQ = { ...q };
    const nextClk = { ...clk };
    for (const c of ics) {
      const seq = GATES[c.gateType!].sequential!;
      for (let f = 0; f < seq.ffs; f++) {
        const base = f * seq.stride;
        const level = (offset: number) => readPin(c.id, base + offset) ?? true;
        const key = ffKey(c.id, f);
        const clock = readPin(c.id, base + seq.clk);
        const before = clk[key];
        if (clock !== undefined) nextClk[key] = clock;
        const edge =
          applyEdges && clock !== undefined && before !== undefined && (seq.edge === "falling" ? before && !clock : !before && clock);
        if (!level(seq.clr)) nextQ[key] = false;
        else if (!level(seq.pre)) nextQ[key] = true;
        else if (edge) {
          if (seq.kind === "d") nextQ[key] = level(seq.d!);
          else {
            const [j, k] = [level(seq.j!), level(seq.k!)];
            nextQ[key] = j && k ? !q[key] : j ? true : k ? false : q[key];
          }
        }
      }
    }
    const changed = ics.some((c) =>
      Array.from({ length: GATES[c.gateType!].sequential!.ffs }, (_, f) => ffKey(c.id, f)).some((k) => nextQ[k] !== q[k]),
    );
    Object.assign(q, nextQ);
    clk = nextClk;
    if (!changed) break;
  }
  return { q, clk };
}
