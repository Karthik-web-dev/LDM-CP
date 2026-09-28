import type { StructuralIssue } from "../../api/validationApi";

interface IssueListProps {
  issues: StructuralIssue[];
  onFocus: (ids: string[]) => void;
}

/** Structural errors/warnings; clicking one highlights the components involved on the canvas. */
export function IssueList({ issues, onFocus }: IssueListProps) {
  if (!issues.length) return null;
  return (
    <ul className="issue-list">
      {issues.map((issue, i) => {
        const ids = [issue.component, ...issue.related].filter((x): x is string => !!x);
        return (
          <li key={i} className={issue.severity}>
            <button type="button" className="issue" onClick={() => onFocus(ids)} disabled={!ids.length}>
              <span className="issue-type">{issue.type.replace(/_/g, " ").toLowerCase()}</span>
              <span>{issue.message}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function ErrorMessage({ message }: { message: string }) {
  return <div className="error-banner" role="alert">{message}</div>;
}
