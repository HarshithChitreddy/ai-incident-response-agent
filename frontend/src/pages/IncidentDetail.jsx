import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../services/api";
import usePolling from "../services/usePolling";
import { duration, fmtTs, pct } from "../services/format";
import { SeverityBadge, StatusBadge } from "../components/Badges";
import Panel, { Empty } from "../components/Panel";
import ConfidenceBar from "../components/ConfidenceBar";

export default function IncidentDetail() {
  const { id } = useParams();
  const [resolving, setResolving] = useState(false);

  const { data: incident } = usePolling(() => api.incident(id), [id], 3000);
  const { data: analysisEnvelope } = usePolling(() => api.analysis(id), [id], 4000);

  if (incident === undefined) return <Empty>loading…</Empty>;
  if (incident === null) return <Empty>Incident not found. <Link to="/">Back to list</Link></Empty>;

  const analysis = analysisEnvelope?.analysis;

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
        <div className="detail-col">
          <Panel
            title="AI analysis"
            right={analysisEnvelope && <span className="muted mono">{analysisEnvelope.model}</span>}
          >
            {!analysis ? (
              <Empty>agent investigating… (auto-refreshes)</Empty>
            ) : (
              <>
                <ConfidenceBar value={analysis.confidence} />
                <h4>Likely root cause</h4>
                <p>{analysis.root_cause}</p>
                {analysis.why_it_might_be_wrong && (
                  <div className="caveat">
                    <h4>Why this might be wrong</h4>
                    <p>{analysis.why_it_might_be_wrong}</p>
                  </div>
                )}
                {analysis.user_impact && (
                  <>
                    <h4>User impact</h4>
                    <p>{analysis.user_impact}</p>
                  </>
                )}
                {(analysis.recommended_runbook_steps || []).length > 0 && (
                  <>
                    <h4>Recommended steps</h4>
                    <ol className="steps">
                      {analysis.recommended_runbook_steps.map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ol>
                  </>
                )}
              </>
            )}
          </Panel>
        </div>

        <div className="detail-col" />
      </div>
    </div>
  );
}
