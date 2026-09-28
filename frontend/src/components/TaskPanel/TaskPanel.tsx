import { useState } from "react";
import type { Task } from "../../api/validationApi";
import { CUSTOM_TASK_ID } from "../TargetEditor/targetDraft";

interface Props {
  tasks: Task[];
  selectedId: string | null;
  task: Task | null; // the active target (exercise or custom); null if a custom target is not defined yet
  onSelect: (id: string) => void;
  onScaffold: () => void;
  onEditTarget: () => void;
}

export function TaskPanel({ tasks, selectedId, task, onSelect, onScaffold, onEditTarget }: Props) {
  const [showHint, setShowHint] = useState(false);
  const custom = selectedId === CUSTOM_TASK_ID;
  return (
    <section className="task-panel" aria-label="Target">
      <div className="task-row">
        <select value={selectedId ?? ""} onChange={(e) => { setShowHint(false); onSelect(e.target.value); }} aria-label="Choose what to validate against">
          <option value={CUSTOM_TASK_ID}>Custom target (equation or truth table)</option>
          <optgroup label="Exercises">
            {tasks.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
          </optgroup>
        </select>
        {custom && <button type="button" onClick={onEditTarget}>Edit target</button>}
        {task && (
          <button type="button" className="ghost" onClick={onScaffold} title="Add any missing input and output components for this target">
            Place inputs &amp; outputs
          </button>
        )}
      </div>
      <div className="task-body">
        {custom && !task && <p className="muted">Define the function you want to build in the <b>Target</b> tab: type an equation or fill in a truth table.</p>}
        {task && <p className="task-desc">{task.description}</p>}
        {task && (
          <p className="task-meta">
            Inputs: <code>{task.inputs.join(", ") || "—"}</code> · Outputs: <code>{(task.outputs.length ? task.outputs : ["Y"]).join(", ")}</code>
            {task.hint && (
              <>
                {" · "}
                <button type="button" className="link" onClick={() => setShowHint((s) => !s)}>{showHint ? "Hide hint" : "Show hint"}</button>
              </>
            )}
          </p>
        )}
        {showHint && task?.hint && <p className="task-hint">{task.hint}</p>}
      </div>
    </section>
  );
}
