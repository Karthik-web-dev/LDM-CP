/** Displays a Boolean expression with operators de-emphasised so the structure is easy to scan. */
export function BooleanExpression({ expression }: { expression: string | null }) {
  if (expression === null) return <span className="expr muted">(too long to display)</span>;
  const parts = expression.split(/(\bAND\b|\bOR\b|\bNOT\b|\bXOR\b|\bNAND\b|\bNOR\b|\bXNOR\b|[()])/g).filter(Boolean);
  return (
    <code className="expr">
      {parts.map((p, i) =>
        /^(AND|OR|NOT|XOR|NAND|NOR|XNOR)$/.test(p) ? <span key={i} className="op">{p}</span>
          : p === "(" || p === ")" ? <span key={i} className="paren">{p}</span>
          : <span key={i}>{p}</span>,
      )}
    </code>
  );
}
