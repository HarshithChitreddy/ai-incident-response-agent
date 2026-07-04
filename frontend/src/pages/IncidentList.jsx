import { Link } from "react-router-dom";
import { api } from "../services/api";
import usePolling from "../services/usePolling";
import { fmtTs, timeAgo } from "../services/format";
import { SeverityBadge, StatusBadge } from "../components/Badges";
import { Empty } from "../components/Panel";

export default function IncidentList() {
  const { data: incidents, error } = usePolling(() => api.incidents(), [], 4000);

  if (error) return <Empty>API unreachable — is the backend running? ({String(error.message)})</Empty>;
  if (incidents === undefined) return <Empty>loading…</Empty>;

  const open = incidents.filter((i) => i.status !== "resolved");
  const critical = open.filter((i) => i.severity === "critical");

  return (
    <div className="page">
      <div className="stats-row">
        <div className="stat">
          <span className="stat-value">{open.length}</span>
          <span className="stat-label">open incidents</span>
        </div>
        <div className="stat stat-critical">
          <span className="stat-value">{critical.length}</span>
          <span className="stat-label">critical</span>
        </div>
        <div className="stat">
          <span className="stat-value">{incidents.length}</span>
          <span className="stat-label">total tracked</span>
        </div>
      </div>

      {incidents.length === 0 ? (
        <Empty>
          No incidents yet. Fire one with{" "}
          <code>python scripts/send_alert.py high_error_rate</code>
        </Empty>
      ) : (
        <table className="incident-table">
          <thead>
            <tr>
              <th>severity</th>
              <th>status</th>
              <th>service</th>
              <th>alert</th>
              <th>title</th>
              <th>started</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((incident) => (
              <tr key={incident.id}>
                <td><SeverityBadge severity={incident.severity} /></td>
                <td><StatusBadge status={incident.status} /></td>
                <td className="mono">{incident.service}</td>
                <td className="mono">{incident.alertname}</td>
                <td>
                  <Link to={`/incidents/${incident.id}`} className="incident-link">
                    {incident.title}
                  </Link>
                </td>
                <td title={fmtTs(incident.started_at)}>{timeAgo(incident.started_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
