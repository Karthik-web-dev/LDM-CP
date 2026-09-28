import type { OutputComparison, TruthTable as Table } from "../../api/validationApi";

interface Props {
  table: Table;
  expected: Table | null;
  comparisons: OutputComparison[];
}

/** Side-by-side truth table: your circuit's outputs next to the expected outputs; mismatched rows are highlighted. */
export function TruthTable({ table, expected, comparisons }: Props) {
  const pairs = comparisons
    .filter((c) => c.circuit_output !== null)
    .map((c) => ({
      label: c.expected_output,
      actual: table.outputs.indexOf(c.circuit_output!),
      expected: expected ? expected.outputs.indexOf(c.expected_output) : -1,
    }));
  const unchecked = table.outputs.filter((o) => !comparisons.some((c) => c.circuit_output === o));

  return (
    <div className="truth-table-wrap">
      <table className="truth-table">
        <thead>
          <tr>
            {table.variables.map((v) => <th key={v} className="in">{v}</th>)}
            {pairs.map((p) => (
              <th key={p.label} colSpan={2} className="out-group">{p.label}</th>
            ))}
            {unchecked.map((o) => <th key={o}>{o}</th>)}
          </tr>
          <tr className="sub">
            {table.variables.map((v) => <th key={v} />)}
            {pairs.map((p) => [<th key={`${p.label}a`}>yours</th>, <th key={`${p.label}e`}>expected</th>])}
            {unchecked.map((o) => <th key={o}>yours</th>)}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => {
            const erow = expected?.rows[i];
            const bad = pairs.some((p) => {
              const e = erow && p.expected >= 0 ? erow.outputs[p.expected] : null;
              return e !== null && row.outputs[p.actual] !== e; // null = don't care
            });
            return (
              <tr key={i} className={bad ? "mismatch" : ""}>
                {row.inputs.map((v, j) => <td key={j} className="in">{v}</td>)}
                {pairs.map((p) => {
                  const a = row.outputs[p.actual];
                  const e = erow && p.expected >= 0 ? erow.outputs[p.expected] : undefined;
                  return [
                    <td key={`${p.label}a`} className={`val ${e !== undefined && e !== null && a !== e ? "wrong" : ""}`}>{a}</td>,
                    <td key={`${p.label}e`} className="val expected" title={e === null ? "Don't care: any value is accepted" : undefined}>
                      {e === null ? "X" : (e ?? "–")}
                    </td>,
                  ];
                })}
                {unchecked.map((o) => <td key={o} className="val">{row.outputs[table.outputs.indexOf(o)]}</td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
