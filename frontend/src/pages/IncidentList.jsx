import { api } from "../services/api";
import usePolling from "../services/usePolling";
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
        <div className="stat">
          <span className="stat-value">{critical.length}</span>
          <span className="stat-label">critical</span>
        </div>
        <div className="stat">
          <span className="stat-value">{incidents.length}</span>
          <span className="stat-label">total tracked</span>
        </div>
      </div>
    </div>
  );
}
