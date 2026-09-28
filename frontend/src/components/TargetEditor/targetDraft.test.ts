import { describe, expect, it } from "vitest";
import { defaultDraft, draftProblems, draftToTask, nextCell, parseNames, reshapeCells, rowBits, type TargetDraft } from "./targetDraft";

const tableDraft = (patch: Partial<TargetDraft> = {}): TargetDraft => ({ ...defaultDraft(), mode: "table", ...patch });

describe("target draft", () => {
  it("parses name lists with commas or spaces", () => {
    expect(parseNames(" A, B  Cin,,")).toEqual(["A", "B", "Cin"]);
  });

  it("cycles cells 0 -> 1 -> X -> 0", () => {
    expect([nextCell(0), nextCell(1), nextCell("X")]).toEqual([1, "X", 0]);
  });

  it("lists row bits with the first input as the most significant bit", () => {
    expect(rowBits(5, 3)).toEqual([1, 0, 1]);
  });

  it("keeps cells when renaming, resets them when the row count changes", () => {
    const d = tableDraft({ cells: { Y: [0, 1, 1, 0] } });
    expect(reshapeCells(d, ["P", "Q"], ["Z"])).toEqual({ Z: [0, 1, 1, 0] });
    expect(reshapeCells(d, ["A", "B", "C"], ["Y"])).toEqual({ Y: [0, 0, 0, 0, 0, 0, 0, 0] });
    expect(reshapeCells(d, ["A", "B"], ["Y", "Y2"])).toEqual({ Y: [0, 1, 1, 0], Y2: [0, 0, 0, 0] });
  });

  it("builds a truth-table task", () => {
    const task = draftToTask(tableDraft({ cells: { Y: [0, 1, 1, "X"] } }));
    expect(task).toMatchObject({ inputs: ["A", "B"], outputs: ["Y"], expected_truth_table: { Y: [0, 1, 1, "X"] } });
    expect(task.expected_outputs).toBeUndefined();
  });

  it("builds an equation task using the preview's input order", () => {
    const d: TargetDraft = { ...defaultDraft(), equations: [{ label: "S", expr: "A ^ B" }, { label: "C", expr: "A B" }] };
    const task = draftToTask(d, ["A", "B"]);
    expect(task).toMatchObject({ inputs: ["A", "B"], outputs: ["S", "C"], expected_outputs: { S: "A ^ B", C: "A B" } });
  });

  it("reports obvious problems before calling the backend", () => {
    expect(draftProblems(defaultDraft())).toContain("Type an equation for every output.");
    expect(draftProblems({ ...defaultDraft(), equations: [{ label: "Y", expr: "A" }, { label: "Y", expr: "B" }] })).toContain("Output names must be different.");
    expect(draftProblems(tableDraft({ tableInputs: ["A", "A"] }))).toContain("Input names must be different.");
    expect(draftProblems(tableDraft({ tableInputs: ["A", "B", "C", "D", "E", "F", "G"] }))[0]).toMatch(/at most 6/);
    expect(draftProblems(tableDraft())).toEqual([]);
  });
});
