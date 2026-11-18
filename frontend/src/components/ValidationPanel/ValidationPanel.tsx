import type { AIFeedback, AIMode, SequenceResult, Target, ValidateResponse } from "../../api/validationApi";
import type { NormalizedCircuit } from "../../circuit/circuitTypes";
import { BooleanExpression } from "../BooleanExpression/BooleanExpression";
import { ErrorMessage, IssueList } from "../ErrorMessage/ErrorMessage";
import { KMapPanel } from "../KMap/KMap";
import { TruthTable } from "../TruthTable/TruthTable";
import "./ValidationPanel.css";

export type Phase = "idle" | "analyzing" | "feedback" | "done";

interface Props {
  phase: Phase;
  result: ValidateResponse | null;
  ai: AIFeedback | null;
  aiMode: AIMode;
  error: string | null;
  stale: boolean;
  onFocus: (ids: string[]) => void;
  onHint: () => void;
  kmapTarget: Target | null;
  circuit: NormalizedCircuit;
  circuitVersion: string;
  /** Sequential exercises have no truth table or K-map. */
  sequential?: boolean;
}

export function ValidationPanel({ phase, result, ai, aiMode, error, stale, onFocus, onHint, kmapTarget, circuit, circuitVersion, sequential }: Props) {
  if (error) return <ErrorMessage message={error} />;
  if (phase === "analyzing" && !result) return <p className="status-line"><Spinner /> Analyzing circuit…</p>;
  if (phase === "feedback" && !result) return <p className="status-line"><Spinner /> Asking the tutor…</p>;
  if (!result) {
    return (
      <div className="panel-empty">
        <h2>Nothing checked yet</h2>
        <p>Build a circuit for the target, then press <strong>Validate</strong>. Stuck? Press <strong>Hint</strong> at any time.</p>
        <p className="muted small">
          The circuit analysis is exact: its Boolean expression and complete truth table are computed from your wiring.
          The AI tutor only explains the result.
        </p>
        {!sequential && (
          <div className="panel-empty-kmap">
            <KMapPanel target={kmapTarget} version={circuitVersion} />
          </div>
        )}
      </div>
    );
  }

  const det = result.deterministic;
  const complete = det.structurally_valid && det.errors.length === 0;
  const status = result.is_correct ? "ok" : complete ? "bad" : "warn";

  return (
    <div className="results">
      {stale && <div className="stale-banner">The circuit changed since this check. Validate again to update.</div>}

      <div className={`verdict ${status}`}>
        <span className="verdict-icon" aria-hidden>{result.is_correct ? "✓" : complete ? "✕" : "!"}</span>
        <div>
          <div className="verdict-title">{result.is_correct ? "Correct" : complete ? "Not correct yet" : "Circuit incomplete"}</div>
          <div className="verdict-sub">
            {result.is_correct
              ? det.sequence ? "Matches the expected outputs on every clock pulse." : "Matches the target for every input combination."
              : complete
                ? det.sequence ? "Your circuit works, but it does not follow the expected sequence." : "Your circuit works, but it computes a different function from the target."
                : "Fix the problems below so the circuit can be analysed."}
          </div>
        </div>
      </div>

      <section className="card">
        <header className="card-head">
          <h2>Circuit analysis</h2>
          <span className="tag tag-exact">Exact</span>
        </header>

        {det.errors.length === 0 && det.structurally_valid ? (
          <p className="check ok">Structure is valid</p>
        ) : (
          <>
            <p className="check bad">{det.errors.length} problem{det.errors.length === 1 ? "" : "s"} found</p>
            <IssueList issues={det.errors} onFocus={onFocus} />
          </>
        )}
        {det.warnings.length > 0 && (
          <details className="warnings" open={det.warnings.length <= 3}>
            <summary>{det.warnings.length} warning{det.warnings.length === 1 ? "" : "s"}</summary>
            <IssueList issues={det.warnings} onFocus={onFocus} />
          </details>
        )}

        {det.comparisons.map((c) => (
          <div key={c.expected_output} className="comparison">
            <h3>Output {c.expected_output}</h3>
            <dl>
              <dt>You built</dt>
              <dd>{c.circuit_output === null ? <span className="muted">No output labelled {c.expected_output}</span> : <BooleanExpression expression={c.circuit_expression} />}</dd>
              <dt>Target</dt>
              <dd>
                {c.expected_defined_by === "truth_table" ? (
                  <><span className="muted">truth table ≡ </span><BooleanExpression expression={c.expected_expression} /></>
                ) : (
                  <code className="expr">{c.expected_expression}</code>
                )}
              </dd>
              <dt>Result</dt>
              <dd className={c.equivalent ? "check ok" : "check bad"}>
                {c.equivalent
                  ? "Logically equivalent"
                  : c.circuit_output === null
                    ? "Missing output"
                    : `Differs on ${c.mismatch_count} of ${det.truth_table?.rows.length ?? "?"} rows`}
              </dd>
            </dl>
            {c.counterexamples.length > 0 && (
              <ul className="counterexamples">
                {c.counterexamples.slice(0, 4).map((ce, i) => (
                  <li key={i}>
                    <code>{Object.entries(ce.inputs).map(([k, v]) => `${k}=${v}`).join(" ") || "—"}</code>
                    <span>expected <b>{ce.expected}</b>, got <b className="text-danger">{ce.actual}</b></span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}

        {det.sequence && <SequenceTable sequence={det.sequence} />}

        {det.truth_table && (
          <details className="sub-section" open={det.truth_table.rows.length <= 16}>
            <summary>Truth table <span className="muted">· {det.truth_table.rows.length} rows</span></summary>
            <TruthTable table={det.truth_table} expected={det.expected_truth_table} comparisons={det.comparisons} />
          </details>
        )}

        {!sequential && (
          <div className="sub-section kmap-section">
            <KMapPanel target={kmapTarget} circuit={complete ? circuit : undefined} version={circuitVersion} />
          </div>
        )}
      </section>

      <section className="card card-ai">
        <header className="card-head">
          <h2>{aiMode === "hint" ? "Hint" : "AI tutor"}</h2>
          <span className="tag tag-ai">AI-generated</span>
          <button type="button" className="btn-ghost btn-sm card-head-action" onClick={onHint} disabled={phase === "feedback"}>
            {aiMode === "hint" && ai?.available ? "Another hint" : "Get a hint"}
          </button>
        </header>
        <AIFeedbackView phase={phase} ai={ai} onFocus={onFocus} />
      </section>
    </div>
  );
}

function AIFeedbackView({ phase, ai, onFocus }: { phase: Phase; ai: AIFeedback | null; onFocus: (ids: string[]) => void }) {
  if (phase === "feedback" || (phase === "analyzing" && !ai)) return <p className="status-line"><Spinner /> Asking the tutor…</p>;
  if (!ai) return null;
  if (!ai.available) {
    return <p className={ai.error ? "ai-unavailable error" : "ai-unavailable"}>{ai.skipped_reason ?? ai.error ?? "AI feedback is unavailable."}</p>;
  }

  return (
    <div className="ai-feedback">
      {ai.summary && <p className="ai-summary">{ai.summary}</p>}
      {ai.issues.length > 0 && (
        <>
          <h3>What's wrong</h3>
          <ul className="ai-issues">
            {ai.issues.map((issue, i) => (
              <li key={i}>
                {issue.component_id && (
                  <button type="button" className="chip" onClick={() => onFocus([issue.component_id!])}>{issue.component_id}</button>
                )}
                {issue.explanation}
              </li>
            ))}
          </ul>
        </>
      )}
      {ai.suggestions.length > 0 && (
        <>
          <h3>Next steps</h3>
          <ol className="ai-suggestions">{ai.suggestions.map((s, i) => <li key={i}>{s}</li>)}</ol>
        </>
      )}
      {ai.concept && <p className="ai-concept">{ai.concept}</p>}
      {ai.anomalies.length > 0 && <div className="anomalies">{ai.anomalies.map((a, i) => <p key={i}>{a}</p>)}</div>}
      {ai.model && <p className="ai-model">{ai.model}</p>}
    </div>
  );
}

/** Expected vs actual outputs after each clock pulse. */
function SequenceTable({ sequence }: { sequence: SequenceResult }) {
  const outputs = Object.keys(sequence.rows[0]?.expected ?? {});
  const inputs = [...new Set(sequence.rows.flatMap((r) => Object.keys(r.inputs)))];
  const bits = (values: Record<string, number>) => outputs.map((o) => values[o]).join("");
  return (
    <div className="sub-section sequence">
      <h3>Clock pulses</h3>
      <p className="muted small">
        Every flip-flop, gate output and input starts at 0. Each row applies the inputs,{" "}
        {sequence.clock ? <>gives one full pulse on <code>{sequence.clock}</code>, and reads</> : "lets the circuit settle, and reads"}{" "}
        <code>{outputs.join(" ")}</code>.
      </p>
      <table className="sequence-table">
        <thead>
          <tr>
            <th>Pulse</th>
            {inputs.map((i) => <th key={i}>{i}</th>)}
            <th>Expected</th>
            <th>You got</th>
            <th aria-label="Result" />
          </tr>
        </thead>
        <tbody>
          {sequence.rows.map((r) => (
            <tr key={r.step} className={r.ok ? "" : "bad"}>
              <td>{r.step}</td>
              {inputs.map((i) => <td key={i}>{r.inputs[i] ?? "·"}</td>)}
              <td><code>{bits(r.expected)}</code></td>
              <td><code>{bits(r.actual)}</code></td>
              <td className={r.ok ? "check ok" : "check bad"}>{r.ok ? "✓" : "✕"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Spinner() {
  return <span className="spinner" aria-hidden />;
}
