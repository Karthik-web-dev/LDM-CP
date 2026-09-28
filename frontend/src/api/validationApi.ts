import type { NormalizedCircuit } from "../circuit/circuitTypes";

// Mirrors backend/app/models. The frontend only displays these results; it never computes them.

export interface Task {
  id: string;
  title: string;
  description: string;
  expected_expression?: string | null;
  expected_outputs?: Record<string, string> | null;
  /** Output label -> column over `inputs` in binary counting order; "X" = don't care. */
  expected_truth_table?: Record<string, TruthCell[]> | null;
  inputs: string[];
  outputs: string[];
  hint?: string | null;
}

export type TruthCell = 0 | 1 | "X";

export interface StructuralIssue {
  type: string;
  severity: "error" | "warning";
  component: string | null;
  message: string;
  related: string[];
}

export interface TruthTable {
  variables: string[];
  outputs: string[];
  /** `null` in an output marks a don't-care row of a target table. */
  rows: { inputs: number[]; outputs: (number | null)[] }[];
}

export interface OutputComparison {
  expected_output: string;
  circuit_output: string | null;
  expected_expression: string;
  expected_defined_by: "expression" | "truth_table";
  circuit_expression: string | null;
  equivalent: boolean;
  counterexamples: { inputs: Record<string, number>; expected: number; actual: number }[];
  mismatch_count: number;
}

export interface DeterministicResult {
  structurally_valid: boolean;
  expression: string | null;
  output_expressions: Record<string, string | null>;
  variables: string[];
  truth_table: TruthTable | null;
  expected_truth_table: TruthTable | null;
  equivalent_to_expected: boolean;
  comparisons: OutputComparison[];
  evaluation_order: string[];
  errors: StructuralIssue[];
  warnings: StructuralIssue[];
}

export interface AIFeedback {
  available: boolean;
  skipped_reason: string | null;
  error: string | null;
  error_kind: string | null;
  summary: string | null;
  issues: { component_id: string | null; type: string; explanation: string }[];
  suggestions: string[];
  concept: string | null;
  model_verdict: boolean | null;
  agrees_with_analysis: boolean | null;
  anomalies: string[];
  model: string | null;
}

export interface ValidateResponse {
  success: boolean;
  is_correct: boolean;
  task: Task;
  deterministic: DeterministicResult;
  ai: AIFeedback;
}

export interface TaskPreview {
  valid: boolean;
  errors: string[];
  inputs: string[];
  outputs: string[];
  expressions: Record<string, string>;
  simplified: Record<string, string>;
  truth_table: TruthTable | null;
}

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch (err) {
    if (init?.signal?.aborted) throw err;
    throw new ApiError("Cannot reach the validation server. Is the backend running on port 8000?");
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { loc: unknown[]; msg: string }) => `${d.loc.join(".")}: ${d.msg}`).join("; ");
    } catch {
      /* keep status text */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export const fetchTasks = () => request<Task[]>("/api/v1/tasks");

/** Validate against a built-in exercise (`{ taskId }`) or a user-defined target (`{ task }`). */
export type Target = { taskId: string } | { task: Task };

export type AIMode = "feedback" | "hint";

const targetRef = (target: Target) => ("taskId" in target ? { task_id: target.taskId } : { task: target.task });

export function validateCircuit(target: Target, circuit: NormalizedCircuit, includeAi: boolean, signal?: AbortSignal, aiMode: AIMode = "feedback") {
  return request<ValidateResponse>("/api/v1/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...targetRef(target), circuit, include_ai: includeAi, ai_mode: aiMode }),
    signal,
  });
}

export interface KMapCell { row: number; col: number; minterm: number; value: number | null }
export interface KMapGroup { term: string; expression: string; minterms: number[]; cells: [number, number][] }
export interface KMap {
  output: string;
  variables: string[];
  row_variables: string[];
  col_variables: string[];
  row_labels: string[];
  col_labels: string[];
  cells: KMapCell[][];
  groups: KMapGroup[];
  minimal_sop: string;
  minterms: number[];
  dont_cares: number[];
}
export interface KMapResponse { source: "target" | "circuit"; kmaps: KMap[]; errors: string[] }

/** K-map of the target, or of what the circuit computes. Computed by the backend, no AI. */
export function fetchKMaps(target: Target, source: "target" | "circuit", circuit?: NormalizedCircuit, signal?: AbortSignal) {
  return request<KMapResponse>("/api/v1/kmap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...targetRef(target), source, ...(circuit ? { circuit } : {}) }),
    signal,
  });
}

export function previewTask(task: Task, signal?: AbortSignal) {
  return request<TaskPreview>("/api/v1/tasks/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(task),
    signal,
  });
}

export function outputLabels(task: Task): string[] {
  if (task.expected_truth_table) return Object.keys(task.expected_truth_table);
  if (task.expected_outputs) return Object.keys(task.expected_outputs);
  return [task.outputs[0] ?? "Y"];
}
