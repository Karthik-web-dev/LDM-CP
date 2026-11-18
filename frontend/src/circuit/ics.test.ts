import { describe, expect, it } from "vitest";
import { serializeCircuit } from "./circuitSerializer";
import type { EditorState } from "./circuitTypes";
import { editorReducer, emptyEditorState, type EditorAction } from "./editorReducer";
import { GATES, IC_ORDER } from "./gateLibrary";
import { signalKey, simulate } from "./simulator";

const run = (actions: EditorAction[], start: EditorState = emptyEditorState()) => actions.reduce(editorReducer, start);
const bits = (n: number, width: number) => Array.from({ length: width }, (_, i) => ((n >> (width - 1 - i)) & 1) === 1);

describe("VCC and GND", () => {
  it("have no inputs and drive constant levels", () => {
    expect(GATES.VCC.defaultInputs).toBe(0);
    expect(GATES.VCC.simulate([])).toEqual([true]);
    expect(GATES.GND.simulate([])).toEqual([false]);
  });

  it("light a lamp and serialize with zero inputs", () => {
    const s = run([
      { type: "add", kind: "gate", gateType: "VCC" },
      { type: "add", kind: "output" },
      { type: "connect", from: "gate_1", to: "output_1", pin: 0 },
    ]);
    expect(s.components[0].pinCount).toBe(0);
    expect(simulate(s).get("output_1")).toBe(true);
    expect(serializeCircuit(s).gates[0]).toMatchObject({ type: "VCC", inputs: 0 });
  });
});

describe("74xx ICs", () => {
  it("list pins consistently", () => {
    for (const type of IC_ORDER) {
      const spec = GATES[type];
      expect(spec.block!.inputNames).toHaveLength(spec.defaultInputs);
      expect(spec.block!.outputNames).toHaveLength(spec.outputCount);
      expect(spec.block!.description).toBeTruthy();
    }
  });

  it("74138 drives only the addressed output low, and only when enabled", () => {
    for (let n = 0; n < 8; n++) {
      const [a, b, c] = [bits(n, 3)[2], bits(n, 3)[1], bits(n, 3)[0]];
      const enabled = GATES["74138"].simulate([a, b, c, true, false, false]);
      expect(enabled).toEqual(Array.from({ length: 8 }, (_, k) => k !== n));
      // any enable pin inactive: every output stays high
      expect(GATES["74138"].simulate([a, b, c, false, false, false]).every(Boolean)).toBe(true);
      expect(GATES["74138"].simulate([a, b, c, true, true, false]).every(Boolean)).toBe(true);
      expect(GATES["74138"].simulate([a, b, c, true, false, true]).every(Boolean)).toBe(true);
    }
  });

  it("74153 selects per half with active-low strobes", () => {
    const pins = (a: boolean, b: boolean, g1: boolean, d1: boolean[], g2: boolean, d2: boolean[]) => [a, b, g1, ...d1, g2, ...d2];
    // select B A = 10 (2): half 1 passes D2, half 2 passes its D2 too
    const v = pins(false, true, false, [false, false, true, false], false, [true, true, false, true]);
    expect(GATES["74153"].simulate(v)).toEqual([true, false]);
    // strobe high forces the output low
    const strobed = pins(false, true, true, [false, false, true, false], true, [true, true, true, true]);
    expect(GATES["74153"].simulate(strobed)).toEqual([false, false]);
  });

  it("work in the live preview with a VCC-tied enable", () => {
    let s = run([
      { type: "add", kind: "input" }, // A -> input_1
      { type: "add", kind: "gate", gateType: "74138" }, // gate_1
      { type: "add", kind: "gate", gateType: "VCC" }, // gate_2
      { type: "add", kind: "gate", gateType: "GND" }, // gate_3
      { type: "add", kind: "output" },
      { type: "connect", from: "input_1", to: "gate_1", pin: 0 },
      { type: "connect", from: "gate_2", to: "gate_1", pin: 3 }, // G1 = VCC
      { type: "connect", from: "gate_3", to: "gate_1", pin: 4 }, // /G2A = GND
      { type: "connect", from: "gate_3", to: "gate_1", pin: 5 }, // /G2B = GND
      { type: "connect", from: "gate_3", to: "gate_1", pin: 1 }, // B = GND
      { type: "connect", from: "gate_3", to: "gate_1", pin: 2 }, // C = GND
      { type: "connect", from: "gate_1", fromPin: 1, to: "output_1", pin: 0 }, // /Y1
    ]);
    expect(simulate(s).get("output_1")).toBe(true); // A=0 -> Y0 low, /Y1 high
    s = run([{ type: "toggleInput", id: "input_1" }], s);
    expect(simulate(s).get("output_1")).toBe(false); // A=1 -> /Y1 low
    expect(simulate(s).get(signalKey("gate_1", 0))).toBe(true);
  });
});
