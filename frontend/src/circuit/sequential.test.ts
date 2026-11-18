import { describe, expect, it } from "vitest";
import type { EditorState } from "./circuitTypes";
import { editorReducer, emptyEditorState, type EditorAction } from "./editorReducer";
import { simulate } from "./simulator";

const run = (actions: EditorAction[], start: EditorState = emptyEditorState()) => actions.reduce(editorReducer, start);
const tie = (from: string, to: string, pins: number[]): EditorAction[] => pins.map((pin) => ({ type: "connect", from, to, pin }));

/** 7476 ripple counter: input_1 = CLK, gate_1 = 7476, gate_2 = VCC, output_1 = Q0, output_2 = Q1. */
function rippleCounter(fromQbar: boolean): EditorState {
  return run([
    { type: "add", kind: "input" },
    { type: "add", kind: "gate", gateType: "7476" },
    { type: "add", kind: "gate", gateType: "VCC" },
    { type: "add", kind: "output" },
    { type: "add", kind: "output" },
    { type: "connect", from: "input_1", to: "gate_1", pin: 0 },
    ...tie("gate_2", "gate_1", [1, 2, 3, 4, 6, 7, 8, 9]),
    { type: "connect", from: "gate_1", fromPin: fromQbar ? 1 : 0, to: "gate_1", pin: 5 },
    { type: "connect", from: "gate_1", fromPin: 0, to: "output_1", pin: 0 },
    { type: "connect", from: "gate_1", fromPin: 2, to: "output_2", pin: 0 },
  ]);
}

const count = (s: EditorState) => {
  const v = simulate(s);
  return (v.get("output_2") ? 2 : 0) + (v.get("output_1") ? 1 : 0);
};
const pulse = (s: EditorState) => editorReducer(s, { type: "pulse", id: "input_1" });

describe("flip-flop simulation", () => {
  it("counts up as a ripple counter, one step per falling clock edge", () => {
    let s = rippleCounter(false);
    expect(count(s)).toBe(0);
    const seen = [];
    for (let i = 0; i < 5; i++) {
      s = pulse(s);
      seen.push(count(s));
    }
    expect(seen).toEqual([1, 2, 3, 0, 1]);
  });

  it("counts down when the second flip-flop is clocked from /Q", () => {
    let s = rippleCounter(true);
    const seen = [];
    for (let i = 0; i < 5; i++) {
      s = pulse(s);
      seen.push(count(s));
    }
    expect(seen).toEqual([3, 2, 1, 0, 3]);
  });

  it("only triggers on the falling edge: raising the clock does nothing", () => {
    let s = rippleCounter(false);
    s = editorReducer(s, { type: "toggleInput", id: "input_1" }); // 0 -> 1
    expect(count(s)).toBe(0);
    s = editorReducer(s, { type: "toggleInput", id: "input_1" }); // 1 -> 0
    expect(count(s)).toBe(1);
  });

  it("resets with the reset action and holds at 0 while /CLR is low", () => {
    let s = pulse(rippleCounter(false));
    expect(count(s)).toBe(1);
    s = editorReducer(s, { type: "resetSequential" });
    expect(count(s)).toBe(0);

    // Replace the /1CLR and /2CLR ties by GND: the counter cannot leave 0.
    s = run([
      { type: "add", kind: "gate", gateType: "GND" }, // gate_3
      ...tie("gate_3", "gate_1", [2, 7]),
    ], s);
    for (let i = 0; i < 4; i++) s = pulse(s);
    expect(count(s)).toBe(0);
  });

  it("does not treat editing the wiring as a clock pulse", () => {
    let s = rippleCounter(false);
    s = run([{ type: "add", kind: "input" }, { type: "connect", from: "input_2", to: "gate_1", pin: 3 }], s);
    expect(count(s)).toBe(0);
  });

  it("shifts bits through two 7474 D flip-flops on the rising edge", () => {
    // input_1 = CLK, input_2 = DIN, gate_1/gate_2 = 7474, gate_3 = VCC
    let s = run([
      { type: "add", kind: "input" },
      { type: "add", kind: "input" },
      { type: "add", kind: "gate", gateType: "7474" },
      { type: "add", kind: "gate", gateType: "7474" },
      { type: "add", kind: "gate", gateType: "VCC" },
      { type: "add", kind: "output" },
      { type: "add", kind: "output" },
      { type: "add", kind: "output" },
      { type: "add", kind: "output" },
      { type: "connect", from: "input_2", to: "gate_1", pin: 0 },
      { type: "connect", from: "gate_1", fromPin: 0, to: "gate_1", pin: 4 },
      { type: "connect", from: "gate_1", fromPin: 2, to: "gate_2", pin: 0 },
      { type: "connect", from: "gate_2", fromPin: 0, to: "gate_2", pin: 4 },
      ...["gate_1", "gate_2"].flatMap((ic) => [
        ...tie("input_1", ic, [1, 5]),
        ...tie("gate_3", ic, [2, 3, 6, 7]),
      ]),
      { type: "connect", from: "gate_1", fromPin: 0, to: "output_1", pin: 0 }, // Q0
      { type: "connect", from: "gate_1", fromPin: 2, to: "output_2", pin: 0 }, // Q1
      { type: "connect", from: "gate_2", fromPin: 0, to: "output_3", pin: 0 }, // Q2
      { type: "connect", from: "gate_2", fromPin: 2, to: "output_4", pin: 0 }, // Q3
    ]);
    const word = () => {
      const v = simulate(s);
      return ["output_4", "output_3", "output_2", "output_1"].map((id) => (v.get(id) ? "1" : "0")).join("");
    };
    const seen = [];
    for (const din of [true, false, true, true]) {
      if (!!s.inputValues.input_2 !== din) s = editorReducer(s, { type: "toggleInput", id: "input_2" });
      s = pulse(s);
      seen.push(word());
    }
    expect(seen).toEqual(["0001", "0010", "0101", "1011"]);
  });
});
