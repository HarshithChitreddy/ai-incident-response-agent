const BASE = "/api/v1";

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (res.status === 404) return null; // not-yet-available resources (analysis, postmortem)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  incidents: (status) => get(`/incidents${status ? `?status=${status}` : ""}`),
  incident: (id) => get(`/incidents/${id}`),
  analysis: (id) => get(`/incidents/${id}/analysis`),
  trace: (id) => get(`/incidents/${id}/trace`),
  slack: (id) => get(`/incidents/${id}/slack`),
  postmortem: (id) => get(`/incidents/${id}/postmortem`),
  runs: (id) => get(`/incidents/${id}/runs`),
  resolve: async (id) => {
    const res = await fetch(`${BASE}/incidents/${id}/resolve`, { method: "POST" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  },
};
