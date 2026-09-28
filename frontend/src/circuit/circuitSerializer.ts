import type { EditorState, NormalizedCircuit } from "./circuitTypes";

/**
 * Editor state -> normalized circuit JSON (schema version 1).
 *
 * This is the only place that knows both the editor model and the API contract. The output is
 * deterministic: components keep creation order and ids are stable. Positions are included only
 * as display metadata; semantics come from ids and connections.
 */
export function serializeCircuit(state: EditorState): NormalizedCircuit {
  const byId = new Map(state.components.map((c) => [c.id, c]));
  const pos = (x: number, y: number) => ({ x: Math.round(x), y: Math.round(y) });

  return {
    version: 1,
    inputs: state.components
      .filter((c) => c.kind === "input")
      .map((c) => ({ id: c.id, label: c.label ?? c.id, position: pos(c.x, c.y) })),
    gates: state.components
      .filter((c) => c.kind === "gate")
      .map((c) => ({ id: c.id, type: c.gateType ?? "UNKNOWN", inputs: c.pinCount, position: pos(c.x, c.y) })),
    outputs: state.components
      .filter((c) => c.kind === "output")
      .map((c) => ({ id: c.id, label: c.label ?? c.id, position: pos(c.x, c.y) })),
    connections: state.wires.map((w) => {
      const target = byId.get(w.to);
      // Gate pins are always explicit; outputs have a single pin.
      return target?.kind === "gate" ? { from: w.from, to: w.to, input_index: w.pin } : { from: w.from, to: w.to };
    }),
  };
}

/** Normalized circuit JSON -> editor state (used to load saved or example circuits). */
export function deserializeCircuit(circuit: NormalizedCircuit): EditorState {
  const maxIndex = (ids: string[], prefix: string) =>
    ids.reduce((m, id) => {
      const match = id.match(new RegExp(`^${prefix}_(\\d+)$`));
      return match ? Math.max(m, Number(match[1])) : m;
    }, 0);

  let fallbackY = 40;
  const at = (p?: { x: number; y: number }) => p ?? { x: 40, y: (fallbackY += 60) };

  const components: EditorState["components"] = [
    ...circuit.inputs.map((i) => ({ id: i.id, kind: "input" as const, label: i.label, pinCount: 0, ...at(i.position) })),
    ...circuit.gates.map((g) => ({
      id: g.id,
      kind: "gate" as const,
      gateType: g.type.toUpperCase() as EditorState["components"][number]["gateType"],
      pinCount: g.inputs,
      ...at(g.position),
    })),
    ...circuit.outputs.map((o) => ({ id: o.id, kind: "output" as const, label: o.label, pinCount: 1, ...at(o.position) })),
  ];
  const wires = circuit.connections.map((c, i) => ({ id: `wire_${i + 1}`, from: c.from, to: c.to, pin: c.input_index ?? 0 }));

  return {
    components,
    wires,
    inputValues: {},
    counters: {
      input: maxIndex(circuit.inputs.map((i) => i.id), "input"),
      gate: maxIndex(circuit.gates.map((g) => g.id), "gate"),
      output: maxIndex(circuit.outputs.map((o) => o.id), "output"),
      wire: wires.length,
    },
  };
}
