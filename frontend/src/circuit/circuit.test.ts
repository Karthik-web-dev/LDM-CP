import { describe, expect, it } from "vitest";
import { deserializeCircuit, serializeCircuit } from "./circuitSerializer";
import type { EditorState } from "./circuitTypes";
import { editorReducer, emptyEditorState, type EditorAction } from "./editorReducer";
import { simulate } from "./simulator";

const run = (actions: EditorAction[], start: EditorState = emptyEditorState()) => actions.reduce(editorReducer, start);

/** A AND B -> Y, built through editor actions. */
function andCircuit(): EditorState {
  return run([
    { type: "add", kind: "input" },
    { type: "add", kind: "input" },
    { type: "add", kind: "gate", gateType: "AND" },
    { type: "add", kind: "output" },
    { type: "connect", from: "input_1", to: "gate_1", pin: 0 },
    { type: "connect", from: "input_2", to: "gate_1", pin: 1 },
    { type: "connect", from: "gate_1", to: "output_1", pin: 0 },
  ]);
}

describe("editor reducer", () => {
  it("assigns stable ids and default labels", () => {
    const s = andCircuit();
    expect(s.components.map((c) => [c.id, c.label ?? c.gateType])).toEqual([
      ["input_1", "A"], ["input_2", "B"], ["gate_1", "AND"], ["output_1", "Y"],
    ]);
  });

  it("never reuses ids after deletion", () => {
    const s = run([{ type: "remove", id: "gate_1" }, { type: "add", kind: "gate", gateType: "OR" }], andCircuit());
    expect(s.components.some((c) => c.id === "gate_2")).toBe(true);
    expect(s.components.some((c) => c.id === "gate_1")).toBe(false);
  });

  it("removes wires attached to a deleted component", () => {
    const s = run([{ type: "remove", id: "gate_1" }], andCircuit());
    expect(s.wires).toEqual([]);
  });

  it("replaces the existing driver when rewiring a pin", () => {
    const s = run([{ type: "connect", from: "input_1", to: "gate_1", pin: 1 }], andCircuit());
    expect(s.wires.filter((w) => w.to === "gate_1").map((w) => [w.from, w.pin])).toEqual([
      ["input_1", 0], ["input_1", 1],
    ]);
  });

  it("rejects connections to nonexistent pins or from outputs", () => {
    const s = andCircuit();
    expect(run([{ type: "connect", from: "input_1", to: "gate_1", pin: 5 }], s)).toBe(s);
    expect(run([{ type: "connect", from: "output_1", to: "gate_1", pin: 0 }], s)).toBe(s);
  });

  it("drops wires to pins that disappear when shrinking a gate", () => {
    const s = run([
      { type: "setPinCount", id: "gate_1", pinCount: 3 },
      { type: "connect", from: "input_1", to: "gate_1", pin: 2 },
      { type: "setPinCount", id: "gate_1", pinCount: 2 },
    ], andCircuit());
    expect(s.wires.some((w) => w.pin === 2)).toBe(false);
  });

  it("scaffolds task inputs and outputs without duplicating", () => {
    const s = run([
      { type: "scaffold", inputs: ["A", "B", "Cin"], outputs: ["S", "Cout"] },
      { type: "scaffold", inputs: ["A", "B", "Cin"], outputs: ["S", "Cout"] },
    ]);
    expect(s.components.map((c) => c.label)).toEqual(["A", "B", "Cin", "S", "Cout"]);
  });
});

describe("serializer", () => {
  it("produces the normalized schema with explicit pins", () => {
    const json = serializeCircuit(andCircuit());
    expect(json.version).toBe(1);
    expect(json.inputs.map(({ id, label }) => ({ id, label }))).toEqual([
      { id: "input_1", label: "A" }, { id: "input_2", label: "B" },
    ]);
    expect(json.gates.map(({ id, type, inputs }) => ({ id, type, inputs }))).toEqual([{ id: "gate_1", type: "AND", inputs: 2 }]);
    expect(json.outputs.map((o) => o.label)).toEqual(["Y"]);
    expect(json.connections).toEqual([
      { from: "input_1", to: "gate_1", input_index: 0 },
      { from: "input_2", to: "gate_1", input_index: 1 },
      { from: "gate_1", to: "output_1" },
    ]);
  });

  it("is deterministic", () => {
    expect(JSON.stringify(serializeCircuit(andCircuit()))).toBe(JSON.stringify(serializeCircuit(andCircuit())));
  });

  it("round-trips through deserialize", () => {
    const json = serializeCircuit(andCircuit());
    const back = deserializeCircuit(json);
    expect(serializeCircuit(back)).toEqual(json);
    // Counters continue after loaded ids.
    const next = run([{ type: "add", kind: "gate", gateType: "OR" }], back);
    expect(next.components.at(-1)?.id).toBe("gate_2");
  });
});

describe("live simulation", () => {
  it("propagates switch values", () => {
    let s = andCircuit();
    expect(simulate(s).get("output_1")).toBe(false);
    s = run([{ type: "toggleInput", id: "input_1" }, { type: "toggleInput", id: "input_2" }], s);
    expect(simulate(s).get("output_1")).toBe(true);
  });

  it("reports unknown for unfinished circuits", () => {
    const s = run([{ type: "removeWire", id: "wire_2" }], andCircuit());
    expect(simulate(s).get("gate_1")).toBeUndefined();
    expect(simulate(s).get("output_1")).toBeUndefined();
  });

  it("terminates on feedback loops", () => {
    const s = run([
      { type: "add", kind: "gate", gateType: "NOT" },
      { type: "connect", from: "gate_2", to: "gate_2", pin: 0 },
    ], andCircuit());
    expect(() => simulate(s)).not.toThrow();
  });
});
