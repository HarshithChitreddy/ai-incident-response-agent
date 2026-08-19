const SEVERITY_CLASS = {
  critical: "sev-critical",
  high: "sev-high",
  medium: "sev-medium",
  low: "sev-low",
  warning: "sev-warning",
};

export function SeverityBadge({ severity }) {
  return (
    <span className={`badge ${SEVERITY_CLASS[severity] || "sev-warning"}`}>
      {severity || "unknown"}
    </span>
  );
}

export function StatusBadge({ status }) {
  return <span className={`badge status-${status}`}>{status}</span>;
}
