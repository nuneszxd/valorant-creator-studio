import { fmtNumber, prettyKey } from "../lib/format";

function isUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

/** Renders any JSON-like value as a compact, readable nested list (used for observed radar data). */
export function DataTree({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="muted">–</span>;
  if (typeof value === "number") return <span>{fmtNumber(value)}</span>;
  if (typeof value === "boolean") return <span>{value ? "sim" : "não"}</span>;
  if (typeof value === "string") {
    return isUrl(value) ? (
      <a href={value} target="_blank" rel="noreferrer noopener">
        {value}
      </a>
    ) : (
      <span>{value}</span>
    );
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="muted">(vazio)</span>;
    return (
      <ul className="tree">
        {value.map((item, i) => (
          <li key={i}>
            <DataTree value={item} />
          </li>
        ))}
      </ul>
    );
  }
  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) return <span className="muted">(vazio)</span>;
  return (
    <dl className="tree-dl">
      {entries.map(([key, val]) => (
        <div key={key} className="tree-row">
          <dt>{prettyKey(key)}</dt>
          <dd>
            <DataTree value={val} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
