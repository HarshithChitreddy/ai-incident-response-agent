export function SeverityBadge({ severity }) {
  return <span className={`badge badge-${severity || "unknown"}`}>{severity || "unknown"}</span>;
}

export function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}
