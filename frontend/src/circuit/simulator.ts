import { GATES } from "./gateLibrary";
import type { EditorState } from "./circuitTypes";

/** Signal value on a component's output: true/false, or undefined when it cannot be determined. */
export type SignalMap = Map<string, boolean | undefined>;

/**
 * Live preview simulation for the editor: which wires and lamps are lit for the current switch
 * positions. This is interaction feedback only. Boolean expressions, truth tables, and
 * correctness always come from the backend.
 *
 * Values propagate by repeated relaxation, so an unfinished or looping circuit settles to
 * "unknown" instead of hanging.
 */
export function simulate(state: EditorState): SignalMap {
  const values: SignalMap = new Map();
  const drivers = new Map<string, Map<number, string[]>>();
  for (const w of state.wires) {
    const pins = drivers.get(w.to) ?? new Map<number, string[]>();
    pins.set(w.pin, [...(pins.get(w.pin) ?? []), w.from]);
    drivers.set(w.to, pins);
  }

  const readPin = (id: string, pin: number): boolean | undefined => {
    const sources = drivers.get(id)?.get(pin) ?? [];
    return sources.length === 1 ? values.get(sources[0]) : undefined;
  };

  for (const c of state.components) {
    if (c.kind === "input") values.set(c.id, state.inputValues[c.id] ?? false);
  }

  for (let pass = 0; pass <= state.components.length; pass++) {
    let changed = false;
    for (const c of state.components) {
      if (c.kind === "input") continue;
      let next: boolean | undefined;
      if (c.kind === "output") {
        next = readPin(c.id, 0);
      } else {
        const spec = c.gateType ? GATES[c.gateType] : undefined;
        const ins = Array.from({ length: c.pinCount }, (_, i) => readPin(c.id, i));
        next = spec && ins.every((v) => v !== undefined) ? spec.simulate(ins as boolean[]) : undefined;
      }
      if (values.get(c.id) !== next) {
        values.set(c.id, next);
        changed = true;
      }
    }
    if (!changed) break;
  }
  return values;
}
