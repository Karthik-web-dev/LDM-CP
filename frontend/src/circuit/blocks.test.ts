import { describe, expect, it } from "vitest";
import { deserializeCircuit, serializeCircuit } from "./circuitSerializer";
import type { EditorState, GateType } from "./circuitTypes";
import { editorReducer, emptyEditorState, type EditorAction } from "./editorReducer";
import { BLOCK_ORDER, GATES } from "./gateLibrary";
import { signalKey, simulate } from "./simulator";

const run = (actions: EditorAction[], start: EditorState = emptyEditorState()) => actions.reduce(editorReducer, start);
const bits = (n: number, width: number) => Array.from({ length: width }, (_, i) => ((n >> (width - 1 - i)) & 1) === 1);

describe("block definitions", () => {
  it("have pin names matching their pin counts", () => {
    for (const type of BLOCK_ORDER) {
      const spec = GATES[type];
      expect(spec.block!.inputNames).toHaveLength(spec.defaultInputs);
      expect(spec.block!.outputNames).toHaveLength(spec.outputCount);
      expect(spec.minInputs).toBe(spec.maxInputs);
    }
  });

  it("MUX4 selects the addressed data input", () => {
    for (let sel = 0; sel < 4; sel++) {
      for (let data = 0; data < 16; data++) {
        const [y] = GATES.MUX4.simulate([...bits(data, 4), ...bits(sel, 2)]);
        expect(y).toBe(bits(data, 4)[sel]);
      }
    }
  });

  it("DEMUX4 routes data to the addressed output only", () => {
    for (let sel = 0; sel < 4; sel++) {
      expect(GATES.DEMUX4.simulate([true, ...bits(sel, 2)])).toEqual([0, 1, 2, 3].map((k) => k === sel));
      expect(GATES.DEMUX4.simulate([false, ...bits(sel, 2)])).toEqual([false, false, false, false]);
    }
  });

  it("DECODER3 is one-hot", () => {
    for (let n = 0; n < 8; n++) {
      expect(GATES.DECODER3.simulate(bits(n, 3))).toEqual(Array.from({ length: 8 }, (_, k) => k === n));
    }
  });

  it("ENCODER8 returns the index of the single active input", () => {
    for (let k = 0; k < 8; k++) {
      const input = Array.from({ length: 8 }, (_, i) => i === k);
      expect(GATES.ENCODER8.simulate(input)).toEqual(bits(k, 3));
    }
  });
});

/** A (switch) -> DEC 2:4 -> lamp on output pin 3 (wired from pin index 3). */
function decoderCircuit(): EditorState {
  return run([
    { type: "add", kind: "input" },
    { type: "add", kind: "input" },
    { type: "add", kind: "gate", gateType: "DECODER2" as GateType },
    { type: "add", kind: "output" },
    { type: "connect", from: "input_1", to: "gate_1", pin: 0 },
    { type: "connect", from: "input_2", to: "gate_1", pin: 1 },
    { type: "connect", from: "gate_1", fromPin: 3, to: "output_1", pin: 0 },
  ]);
}

describe("multi-output blocks in the editor", () => {
  it("light only the addressed output", () => {
    let s = decoderCircuit();
    expect(simulate(s).get("output_1")).toBe(false); // address 00 -> Y0, not Y3
    s = run([{ type: "toggleInput", id: "input_1" }, { type: "toggleInput", id: "input_2" }], s);
    expect(simulate(s).get("output_1")).toBe(true); // address 11 -> Y3
    expect(simulate(s).get(signalKey("gate_1", 3))).toBe(true);
    expect(simulate(s).get(signalKey("gate_1", 0))).toBe(false);
  });

  it("rejects a wire from an output pin the block does not have", () => {
    const s = run([{ type: "connect", from: "gate_1", fromPin: 4, to: "output_1", pin: 0 }], decoderCircuit());
    expect(s.wires.filter((w) => w.fromPin === 4)).toEqual([]);
  });

  it("drops wires from output pins that disappear when the block type changes", () => {
    const s = run([{ type: "setGateType", id: "gate_1", gateType: "DEMUX2" }], decoderCircuit());
    expect(s.wires.some((w) => w.from === "gate_1")).toBe(false);
  });

  it("serializes output_index only for extra output pins and round-trips it", () => {
    const json = serializeCircuit(decoderCircuit());
    expect(json.gates[0]).toMatchObject({ type: "DECODER2", inputs: 2 });
    expect(json.connections.find((c) => c.to === "output_1")).toEqual({ from: "gate_1", to: "output_1", output_index: 3 });
    expect(json.connections.find((c) => c.to === "gate_1" && c.input_index === 0)).not.toHaveProperty("output_index");
    expect(serializeCircuit(deserializeCircuit(json))).toEqual(json);
  });
});
