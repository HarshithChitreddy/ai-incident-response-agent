export function fmtTs(iso) {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 16) + " UTC";
}

export function timeAgo(iso) {
  if (!iso) return "";
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ${minutes % 60}m ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function duration(startIso, endIso) {
  if (!startIso || !endIso) return "—";
  const mins = Math.max(0, Math.floor((new Date(endIso) - new Date(startIso)) / 60000));
  const h = Math.floor(mins / 60);
  return h ? `${h}h ${mins % 60}m` : `${mins}m`;
}

export function pct(value) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "n/a";
}
