import { pct } from "../services/format";

export default function ConfidenceBar({ value }) {
  const width = typeof value === "number" ? Math.round(value * 100) : 0;
  const tone = width >= 75 ? "conf-high" : width >= 45 ? "conf-mid" : "conf-low";
  return (
    <div className="confidence">
      <div className="confidence-track">
        <div className={`confidence-fill ${tone}`} style={{ width: `${width}%` }} />
      </div>
      <span className="confidence-label">{pct(value)} confidence</span>
    </div>
  );
}
