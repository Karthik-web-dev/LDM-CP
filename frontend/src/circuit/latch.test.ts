import { describe, expect, it } from "vitest";
import type { EditorState } from "./circuitTypes";
import { editorReducer, emptyEditorState, type EditorAction } from "./editorReducer";
import { hasSequential, simulate } from "./simulator";

const run = (actions: EditorAction[], start: EditorState = emptyEditorState()) => actions.reduce(editorReducer, start);

/** Cross-coupled NAND latch: input_1 = S, input_2 = R (active low), output_1 = Q, output_2 = Qn. */
function latch(): EditorState {
  return run([
    { type: "add", kind: "input" },
    { type: "add", kind: "input" },
    { type: "add", kind: "gate", gateType: "NAND" }, // gate_1 -> Q
    { type: "add", kind: "gate", gateType: "NAND" }, // gate_2 -> Qn
    { type: "add", kind: "output" },
    { type: "add", kind: "output" },
    { type: "connect", from: "input_1", to: "gate_1", pin: 0 },
    { type: "connect", from: "gate_2", to: "gate_1", pin: 1 },
    { type: "connect", from: "input_2", to: "gate_2", pin: 0 },
    { type: "connect", from: "gate_1", to: "gate_2", pin: 1 },
    { type: "connect", from: "gate_1", to: "output_1", pin: 0 },
    { type: "connect", from: "gate_2", to: "output_2", pin: 0 },
  ]);
}

const qs = (s: EditorState) => {
  const v = simulate(s);
  return `${v.get("output_1") === undefined ? "?" : +!!v.get("output_1")}${v.get("output_2") === undefined ? "?" : +!!v.get("output_2")}`;
};
const toggle = (s: EditorState, id: string) => editorReducer(s, { type: "toggleInput", id });

describe("gate-level latch", () => {
  it("is recognised as memory", () => {
    expect(hasSequential(latch())).toBe(true);
    expect(hasSequential(run([{ type: "add", kind: "gate", gateType: "AND" }]))).toBe(false);
  });

  it("has defined outputs, not unknown ones, even though it is a loop", () => {
    expect(qs(latch())).toBe("11"); // S = R = 0 asserts both active-low inputs
  });

  it("sets, holds, resets and holds again", () => {
    let s = latch();
    s = toggle(s, "input_2"); // S = 0, R = 1: set
    expect(qs(s)).toBe("10");
    s = toggle(s, "input_1"); // S = 1, R = 1: hold
    expect(qs(s)).toBe("10");
    s = toggle(s, "input_2"); // S = 1, R = 0: reset
    expect(qs(s)).toBe("01");
    s = toggle(s, "input_2"); // S = 1, R = 1: hold
    expect(qs(s)).toBe("01");
  });

  it("starts from a known state after Reset", () => {
    let s = toggle(toggle(latch(), "input_2"), "input_1"); // holding Q = 1
    s = editorReducer(s, { type: "resetSequential" });
    expect(qs(s)).toBe("10"); // from all-zero gate outputs with S = R = 1 the latch settles to Q = 1
  });

  it("an oscillating loop does not hang the editor", () => {
    const ring = run([
      { type: "add", kind: "gate", gateType: "NOT" },
      { type: "connect", from: "gate_1", to: "gate_1", pin: 0 },
    ]);
    expect(() => simulate(ring)).not.toThrow();
  });
});
