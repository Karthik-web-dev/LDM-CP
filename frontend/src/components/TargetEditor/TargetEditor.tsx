import { useEffect, useState } from "react";
import { previewTask, type Task, type TaskPreview, type TruthCell } from "../../api/validationApi";
import { BooleanExpression } from "../BooleanExpression/BooleanExpression";
import { KMapPanel } from "../KMap/KMap";
import {
  MAX_TABLE_INPUTS,
  draftProblems,
  draftToTask,
  nextCell,
  parseNames,
  reshapeCells,
  rowBits,
  type TargetDraft,
} from "./targetDraft";
import "./TargetEditor.css";

interface Props {
  draft: TargetDraft;
  onDraftChange: (d: TargetDraft) => void;
  activeTask: Task | null;
  onApply: (task: Task) => void;
}

/** Define the function to validate against, by equation or by truth table. */
export function TargetEditor({ draft, onDraftChange, activeTask, onApply }: Props) {
  const [preview, setPreview] = useState<TaskPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const problems = draftProblems(draft);

  // Ask the backend to interpret the draft (debounced). The frontend never parses equations itself.
  const draftKey = JSON.stringify(draft);
  useEffect(() => {
    if (problems.length) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      previewTask(draftToTask(draft), controller.signal)
        .then((p) => { setPreview(p); setPreviewError(null); })
        .catch((e: Error) => { if (!controller.signal.aborted) { setPreview(null); setPreviewError(e.message); } })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 350);
    return () => { clearTimeout(timer); controller.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey]);

  const update = (patch: Partial<TargetDraft>) => onDraftChange({ ...draft, ...patch });
  const ready = !problems.length && preview?.valid && !loading;
  const candidate = ready ? draftToTask(draft, preview!.inputs) : null;
  const isActive = !!candidate && !!activeTask && JSON.stringify(candidate) === JSON.stringify(activeTask);

  return (
    <div className="target-editor">
      <div className="segmented" role="tablist" aria-label="Define target by">
        <button role="tab" aria-selected={draft.mode === "equation"} className={draft.mode === "equation" ? "active" : ""} onClick={() => update({ mode: "equation" })}>
          Equation
        </button>
        <button role="tab" aria-selected={draft.mode === "table"} className={draft.mode === "table" ? "active" : ""} onClick={() => update({ mode: "table" })}>
          Truth table
        </button>
      </div>

      {draft.mode === "equation" ? <EquationForm draft={draft} update={update} /> : <TableForm draft={draft} update={update} />}

      <div className="target-preview">
        {problems.length > 0 && <ul className="target-problems">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
        {previewError && <p className="target-problems">{previewError}</p>}
        {!problems.length && preview && !preview.valid && <ul className="target-problems">{preview.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
        {!problems.length && preview?.valid && <PreviewView preview={preview} mode={draft.mode} />}
      </div>

      {candidate && <KMapPanel target={{ task: candidate }} version={draftKey} />}

      <div className="target-actions">
        <button type="button" className="primary" disabled={!candidate || isActive} onClick={() => candidate && onApply(candidate)}>
          {isActive ? "✓ Target in use" : "Use this target"}
        </button>
        <span className="muted small">Places any missing inputs and outputs on the canvas.</span>
      </div>
    </div>
  );
}

function EquationForm({ draft, update }: { draft: TargetDraft; update: (p: Partial<TargetDraft>) => void }) {
  const set = (i: number, patch: Partial<{ label: string; expr: string }>) =>
    update({ equations: draft.equations.map((e, j) => (j === i ? { ...e, ...patch } : e)) });
  return (
    <div className="equation-form">
      {draft.equations.map((eq, i) => (
        <div key={i} className="equation-row">
          <input className="eq-label" value={eq.label} maxLength={32} aria-label="Output name" onChange={(e) => set(i, { label: e.target.value.trim() })} />
          <span>=</span>
          <input
            className="eq-expr"
            value={eq.expr}
            placeholder="e.g. (A AND B) OR NOT C   or   A'B + AB'"
            aria-label={`Equation for ${eq.label}`}
            onChange={(e) => set(i, { expr: e.target.value })}
            spellCheck={false}
          />
          {draft.equations.length > 1 && (
            <button type="button" className="ghost icon" aria-label={`Remove ${eq.label}`} onClick={() => update({ equations: draft.equations.filter((_, j) => j !== i) })}>×</button>
          )}
        </div>
      ))}
      <button
        type="button"
        className="ghost small-btn"
        onClick={() => {
          const used = new Set(draft.equations.map((e) => e.label));
          let n = 2;
          while (used.has(`Y${n}`)) n++;
          update({ equations: [...draft.equations, { label: `Y${n}`, expr: "" }] });
        }}
      >
        + Add output
      </button>
      <p className="syntax-help">
        Operators: <code>AND</code> <code>OR</code> <code>NOT</code> <code>XOR</code> <code>NAND</code> <code>NOR</code> <code>XNOR</code>, or{" "}
        <code>·</code>/<code>*</code>/<code>&amp;</code>, <code>+</code>/<code>|</code>, <code>!</code>/<code>~</code>/<code>'</code>, <code>^</code>.
        Terms written next to each other are ANDed, so <code>A'BC + AB'C</code> works, and capital letters written together are separate inputs (<code>BC</code> = B·C).
        Names with lowercase letters, digits or <code>_</code> stay whole (<code>Cin</code>, <code>S1</code>).
      </p>
    </div>
  );
}

function NamesField({ label, value, onCommit }: { label: string; value: string[]; onCommit: (names: string[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  useEffect(() => setText(value.join(", ")), [value.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  const commit = () => onCommit(parseNames(text));
  return (
    <label className="names-field">
      {label}
      <input value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()} spellCheck={false} />
    </label>
  );
}

function TableForm({ draft, update }: { draft: TargetDraft; update: (p: Partial<TargetDraft>) => void }) {
  const n = draft.tableInputs.length;
  const rows = n <= MAX_TABLE_INPUTS ? 2 ** n : 0;
  const setShape = (inputs: string[], outputs: string[]) =>
    update({ tableInputs: inputs, tableOutputs: outputs, cells: reshapeCells(draft, inputs.slice(0, MAX_TABLE_INPUTS), outputs) });
  const setCell = (out: string, row: number, value: TruthCell) =>
    update({ cells: { ...draft.cells, [out]: draft.cells[out].map((c, i) => (i === row ? value : c)) } });
  const fill = (out: string, value: TruthCell) => update({ cells: { ...draft.cells, [out]: draft.cells[out].map(() => value) } });

  return (
    <div className="table-form">
      <div className="names-row">
        <NamesField label="Inputs" value={draft.tableInputs} onCommit={(names) => setShape(names, draft.tableOutputs)} />
        <NamesField label="Outputs" value={draft.tableOutputs} onCommit={(names) => setShape(draft.tableInputs, names)} />
      </div>
      <p className="syntax-help">Click an output cell to cycle <b>0 → 1 → X</b>. X means "don't care": either value is accepted.</p>
      {rows > 0 && (
        <div className="grid-wrap">
          <table className="target-grid">
            <thead>
              <tr>
                {draft.tableInputs.map((v) => <th key={v} className="in">{v}</th>)}
                {draft.tableOutputs.map((o) => (
                  <th key={o} className="out">
                    {o}
                    <span className="fill-btns">
                      <button type="button" title={`Set all ${o} to 0`} onClick={() => fill(o, 0)}>0</button>
                      <button type="button" title={`Set all ${o} to 1`} onClick={() => fill(o, 1)}>1</button>
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: rows }, (_, r) => (
                <tr key={r}>
                  {rowBits(r, n).map((b, j) => <td key={j} className="in">{b}</td>)}
                  {draft.tableOutputs.map((o) => {
                    const c = draft.cells[o]?.[r] ?? 0;
                    return (
                      <td key={o} className="out">
                        <button type="button" className={`cell v${c}`} onClick={() => setCell(o, r, nextCell(c))} aria-label={`${o} at row ${r}: ${c}`}>
                          {c}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PreviewView({ preview, mode }: { preview: TaskPreview; mode: TargetDraft["mode"] }) {
  const t = preview.truth_table!;
  return (
    <div className="preview-body">
      <h4>{mode === "table" ? "As an equation" : "Interpreted as"}</h4>
      <dl>
        {preview.outputs.map((o) => (
          <div key={o} className="preview-eq">
            <dt>{o} =</dt>
            <dd>
              <BooleanExpression expression={preview.expressions[o]} />
              {mode === "equation" && preview.simplified[o] !== preview.expressions[o] && (
                <div className="muted small">simplified: <BooleanExpression expression={preview.simplified[o]} /></div>
              )}
            </dd>
          </div>
        ))}
      </dl>
      <p className="muted small">Inputs: {preview.inputs.join(", ") || "none"}</p>
      {mode === "equation" && t.rows.length <= 64 && (
        <>
          <h4>Truth table</h4>
          <div className="grid-wrap">
            <table className="target-grid readonly">
              <thead>
                <tr>
                  {t.variables.map((v) => <th key={v} className="in">{v}</th>)}
                  {t.outputs.map((o) => <th key={o} className="out">{o}</th>)}
                </tr>
              </thead>
              <tbody>
                {t.rows.map((row, i) => (
                  <tr key={i}>
                    {row.inputs.map((b, j) => <td key={j} className="in">{b}</td>)}
                    {row.outputs.map((v, j) => <td key={j} className={`out v${v ?? "X"}`}>{v ?? "X"}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
