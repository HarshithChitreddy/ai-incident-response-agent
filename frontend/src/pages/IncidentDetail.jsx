import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../services/api";
import usePolling from "../services/usePolling";
import { duration, fmtTs, pct } from "../services/format";
import { SeverityBadge, StatusBadge } from "../components/Badges";
import Panel, { Empty } from "../components/Panel";

export default function IncidentDetail() {
  const { id } = useParams();
  const [resolving, setResolving] = useState(false);

  const { data: incident } = usePolling(() => api.incident(id), [id], 3000);

  if (incident === undefined) return <Empty>loading…</Empty>;
  if (incident === null) return <Empty>Incident not found. <Link to="/">Back to list</Link></Empty>;

  const onResolve = async () => {
    setResolving(true);
    try {
      await api.resolve(id);
    } finally {
      setResolving(false);
    }
  };

  return (
    <div className="page">
      <div className="detail-header">
        <div>
          <nav className="breadcrumb">
            <Link to="/">incidents</Link>
            <span className="sep">/</span>
            <span className="mono">{String(id).slice(0, 8)}</span>
          </nav>
          <h1>{incident.title}</h1>
          <div className="detail-meta">
            <SeverityBadge severity={incident.severity} />
            <StatusBadge status={incident.status} />
            <span className="mono">{incident.service}</span>
            <span className="mono">{incident.alertname}</span>
            <span>started {fmtTs(incident.started_at)}</span>
            {incident.resolved_at && (
              <span>resolved after {duration(incident.started_at, incident.resolved_at)}</span>
            )}
          </div>
        </div>
        {incident.status !== "resolved" && (
          <button className="resolve-btn" onClick={onResolve} disabled={resolving}>
            {resolving ? "resolving…" : "mark resolved"}
          </button>
        )}
      </div>

      <div className="detail-grid">
        <div className="detail-col" />
        <div className="detail-col" />
      </div>
    </div>
  );
}
