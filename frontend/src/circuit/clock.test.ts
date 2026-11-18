import { describe, expect, it } from "vitest";
import { serializeCircuit } from "./circuitSerializer";
import type { EditorState } from "./circuitTypes";
import { editorReducer, emptyEditorState, type EditorAction } from "./editorReducer";
import { CLOCK_HZ_OPTIONS, DEFAULT_CLOCK_HZ, clampClockHz, clockHalfPeriodMs, componentSize } from "./gateLibrary";
import { simulate } from "./simulator";

const run = (actions: EditorAction[], start: EditorState = emptyEditorState()) => actions.reduce(editorReducer, start);

describe("clock source", () => {
  it("is an input named CLK with a default frequency", () => {
    const s = run([{ type: "add", kind: "input", clock: true }]);
    expect(s.components[0]).toMatchObject({ kind: "input", label: "CLK", clockHz: DEFAULT_CLOCK_HZ });
  });

  it("gets unique names when there are several", () => {
    const s = run([{ type: "add", kind: "input", clock: true }, { type: "add", kind: "input", clock: true }, { type: "add", kind: "input" }]);
    expect(s.components.map((c) => c.label)).toEqual(["CLK", "CLK2", "A"]);
  });

  it("changes frequency within limits and only for clock sources", () => {
    let s = run([{ type: "add", kind: "input", clock: true }, { type: "add", kind: "input" }]);
    s = run([{ type: "setClockHz", id: "input_1", hz: 5 }], s);
    expect(s.components[0].clockHz).toBe(5);
    s = run([{ type: "setClockHz", id: "input_1", hz: 9999 }], s);
    expect(s.components[0].clockHz).toBe(20);
    s = run([{ type: "setClockHz", id: "input_2", hz: 5 }], s);
    expect(s.components[1].clockHz).toBeUndefined();
  });

  it("is sent to the checker as an ordinary input, with no extra fields", () => {
    const json = serializeCircuit(run([{ type: "add", kind: "input", clock: true }]));
    expect(json.inputs).toEqual([{ id: "input_1", label: "CLK", position: expect.any(Object) }]);
  });

  it("scaffolding a sequential exercise creates its clock as a clock source", () => {
    const s = run([{ type: "scaffold", inputs: ["CLK", "M"], outputs: ["Q1", "Q0"], clock: "CLK" }]);
    expect(s.components.find((c) => c.label === "CLK")?.clockHz).toBe(DEFAULT_CLOCK_HZ);
    expect(s.components.find((c) => c.label === "M")?.clockHz).toBeUndefined();
  });

  it("toggles like any input, so it clocks flip-flops", () => {
    let s = run([
      { type: "add", kind: "input", clock: true }, // input_1
      { type: "add", kind: "gate", gateType: "7476" }, // gate_1
      { type: "add", kind: "gate", gateType: "VCC" }, // gate_2
      { type: "add", kind: "output" }, // output_1 = Q0
      { type: "connect", from: "input_1", to: "gate_1", pin: 0 },
      ...[1, 2, 3, 4].map((pin): EditorAction => ({ type: "connect", from: "gate_2", to: "gate_1", pin })),
      { type: "connect", from: "gate_1", fromPin: 0, to: "output_1", pin: 0 },
    ]);
    const seen = [];
    for (let i = 0; i < 6; i++) {
      s = editorReducer(s, { type: "toggleInput", id: "input_1" }); // one edge per timer tick
      seen.push(!!simulate(s).get("output_1"));
    }
    // falling edges are on the 2nd, 4th and 6th toggle: Q0 toggles 1, 0, 1
    expect(seen).toEqual([false, true, true, false, false, true]);
  });

  it("has a wider symbol and sensible timing", () => {
    expect(componentSize({ kind: "input", pinCount: 0, clockHz: 1 }).w).toBe(80);
    expect(componentSize({ kind: "input", pinCount: 0 }).w).toBe(64);
    expect(clockHalfPeriodMs(1)).toBe(500);
    expect(clockHalfPeriodMs(10)).toBe(50);
    expect(clampClockHz(Number.NaN)).toBe(DEFAULT_CLOCK_HZ);
    expect(CLOCK_HZ_OPTIONS).toContain(DEFAULT_CLOCK_HZ);
  });
});
