import type { Task, TruthCell } from "../../api/validationApi";

/** Editable state of a user-defined target. Only the backend interprets it. */
export interface TargetDraft {
  mode: "equation" | "table";
  equations: { label: string; expr: string }[];
  tableInputs: string[];
  tableOutputs: string[];
  /** Output label -> one cell per truth-table row. */
  cells: Record<string, TruthCell[]>;
}

export const CUSTOM_TASK_ID = "custom";
export const MAX_TABLE_INPUTS = 6; // 64 rows: the most that stays comfortable to click through

export const defaultDraft = (): TargetDraft => ({
  mode: "equation",
  equations: [{ label: "Y", expr: "" }],
  tableInputs: ["A", "B"],
  tableOutputs: ["Y"],
  cells: { Y: [0, 0, 0, 0] },
});

/** "A, B  C" -> ["A", "B", "C"] (commas and/or spaces separate names). */
export function parseNames(text: string): string[] {
  return text.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
}

export function nextCell(c: TruthCell): TruthCell {
  return c === 0 ? 1 : c === 1 ? "X" : 0;
}

/** Keep cells consistent with the input/output lists. Existing columns are kept when the row count is unchanged. */
export function reshapeCells(draft: TargetDraft, inputs: string[], outputs: string[]): Record<string, TruthCell[]> {
  const rows = 2 ** inputs.length;
  const sameRows = rows === 2 ** draft.tableInputs.length;
  const cells: Record<string, TruthCell[]> = {};
  outputs.forEach((label, i) => {
    const previous = draft.cells[label] ?? draft.cells[draft.tableOutputs[i]];
    cells[label] = sameRows && previous?.length === rows ? [...previous] : Array<TruthCell>(rows).fill(0);
  });
  return cells;
}

/** Row `r` of a truth table as input bits (first input is the most significant bit). */
export function rowBits(row: number, inputCount: number): number[] {
  return Array.from({ length: inputCount }, (_, j) => (row >> (inputCount - 1 - j)) & 1);
}

/** Build the task sent to the backend. Input order for equations comes from the preview. */
export function draftToTask(draft: TargetDraft, previewInputs: string[] = []): Task {
  const base = { id: CUSTOM_TASK_ID, title: "Custom target", hint: null };
  if (draft.mode === "table") {
    return {
      ...base,
      description: "Build a circuit that matches the truth table.",
      inputs: draft.tableInputs,
      outputs: draft.tableOutputs,
      expected_truth_table: Object.fromEntries(draft.tableOutputs.map((o) => [o, draft.cells[o] ?? []])),
    };
  }
  const equations = draft.equations.filter((e) => e.label.trim() || e.expr.trim());
  return {
    ...base,
    description: "Build a circuit for: " + equations.map((e) => `${e.label} = ${e.expr}`).join(";  "),
    inputs: previewInputs,
    outputs: equations.map((e) => e.label.trim()),
    expected_outputs: Object.fromEntries(equations.map((e) => [e.label.trim(), e.expr])),
  };
}

/** Obvious problems caught before asking the backend (the backend re-validates everything). */
export function draftProblems(draft: TargetDraft): string[] {
  const problems: string[] = [];
  const labels = draft.mode === "table" ? draft.tableOutputs : draft.equations.map((e) => e.label.trim());
  if (!labels.length) problems.push("Add at least one output.");
  if (new Set(labels).size !== labels.length) problems.push("Output names must be different.");
  if (draft.mode === "equation") {
    if (draft.equations.some((e) => !e.expr.trim())) problems.push("Type an equation for every output.");
    if (draft.equations.some((e) => !e.label.trim())) problems.push("Give every output a name.");
  } else {
    if (!draft.tableInputs.length) problems.push("Add at least one input.");
    if (draft.tableInputs.length > MAX_TABLE_INPUTS) problems.push(`Use at most ${MAX_TABLE_INPUTS} inputs in the table editor.`);
    if (new Set(draft.tableInputs).size !== draft.tableInputs.length) problems.push("Input names must be different.");
  }
  return problems;
}
