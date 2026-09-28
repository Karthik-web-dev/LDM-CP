import { useEffect, useState } from "react";
import { fetchKMaps, type KMap as KMapData, type KMapResponse, type Target } from "../../api/validationApi";
import type { NormalizedCircuit } from "../../circuit/circuitTypes";
import "./KMap.css";

const GROUP_COLORS = 6; // matches --group-0 .. --group-5

/** One Karnaugh map with its groups. Everything shown here comes from the backend. */
export function KMapView({ kmap }: { kmap: KMapData }) {
  const [active, setActive] = useState<number | null>(null);
  const groupsAt = new Map<string, number[]>();
  kmap.groups.forEach((g, i) => g.cells.forEach(([r, c]) => {
    const key = `${r},${c}`;
    groupsAt.set(key, [...(groupsAt.get(key) ?? []), i]);
  }));

  const rowHead = kmap.row_variables.join("") || "";
  const colHead = kmap.col_variables.join("");

  return (
    <figure className="kmap">
      <figcaption>
        <span className="kmap-output">{kmap.output}</span>
        <span className="kmap-sop">= {kmap.minimal_sop}</span>
      </figcaption>
      <table className="kmap-grid" onMouseLeave={() => setActive(null)}>
        <thead>
          <tr>
            <th className="kmap-corner">
              <span className="corner-row">{rowHead}</span>
              <span className="corner-col">{colHead}</span>
            </th>
            {kmap.col_labels.map((l) => <th key={l} className="kmap-head">{l}</th>)}
          </tr>
        </thead>
        <tbody>
          {kmap.cells.map((row, r) => (
            <tr key={r}>
              <th className="kmap-head">{kmap.row_labels[r] || "—"}</th>
              {row.map((cell) => {
                const groups = groupsAt.get(`${cell.row},${cell.col}`) ?? [];
                const shown = active === null ? groups : groups.filter((g) => g === active);
                const dimmed = active !== null && !groups.includes(active);
                const style = {
                  boxShadow: shown.map((g, i) => `inset 0 0 0 ${2 + i * 3}px var(--group-${g % GROUP_COLORS})`).join(", ") || undefined,
                  background: shown.length ? `var(--group-${shown[0] % GROUP_COLORS}-bg)` : undefined,
                };
                return (
                  <td key={cell.col} className={`kmap-cell v${cell.value ?? "X"} ${dimmed ? "dim" : ""}`} style={style} title={`m${cell.minterm}`}>
                    <span className="kmap-value">{cell.value ?? "X"}</span>
                    <span className="kmap-minterm">{cell.minterm}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {kmap.groups.length > 0 && (
        <ul className="kmap-legend">
          {kmap.groups.map((g, i) => (
            <li
              key={i}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
              tabIndex={0}
              className={active === i ? "active" : ""}
            >
              <span className="swatch" style={{ background: `var(--group-${i % GROUP_COLORS})` }} />
              <code>{g.term}</code>
              <span className="muted">{g.cells.length} cell{g.cells.length === 1 ? "" : "s"}</span>
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}

interface PanelProps {
  target: Target | null;
  circuit?: NormalizedCircuit; // enables the "Your circuit" view
  /** Changes whenever the target or circuit changes, so a shown map is refetched. */
  version: string;
}

/** Fetches and shows K-maps on request, for the target or for the current circuit. */
export function KMapPanel({ target, circuit, version }: PanelProps) {
  const [source, setSource] = useState<"target" | "circuit">("target");
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<KMapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !target) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchKMaps(target, source, source === "circuit" ? circuit : undefined, controller.signal)
      .then(setData)
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, source, version]);

  if (!target) return null;
  if (!open) {
    return <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(true)}>Show K-map</button>;
  }
  return (
    <div className="kmap-panel">
      <div className="kmap-toolbar">
        {circuit ? (
          <div className="segmented segmented-sm" role="tablist" aria-label="K-map of">
            <button role="tab" aria-selected={source === "target"} className={source === "target" ? "active" : ""} onClick={() => setSource("target")}>Target</button>
            <button role="tab" aria-selected={source === "circuit"} className={source === "circuit" ? "active" : ""} onClick={() => setSource("circuit")}>Your circuit</button>
          </div>
        ) : <span className="muted small">K-map of the target</span>}
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>Hide</button>
      </div>
      {loading && !data && <p className="muted small">Computing…</p>}
      {error && <p className="text-danger small">{error}</p>}
      {data?.errors.map((e) => <p key={e} className="muted small">{e}</p>)}
      <div className="kmap-list">{data?.kmaps.map((k) => <KMapView key={k.output} kmap={k} />)}</div>
      {data && data.kmaps.length > 0 && (
        <p className="muted small">Groups are the prime implicants chosen by the simplifier. Hover a term to see its cells. Numbers in the corners are minterm indices.</p>
      )}
    </div>
  );
}
