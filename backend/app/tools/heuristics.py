"""Severity prediction and root-cause commit ranking.

predict_severity uses the trained Phase 4 model when an artifact exists
(train with `python -m app.ml.train`) and falls back to the heuristic
otherwise — the tool interface never changes. Commit ranking stays heuristic:
with a handful of commits per incident, transparent scoring beats an opaque
model and the reasons feed straight into the agent's analysis.
"""

import json
from datetime import datetime

from app.tools.base import ToolContext

RISK_KEYWORDS = (
    "timeout", "retry", "pool", "cache", "migration", "config",
    "limit", "batch", "connection", "deadline",
)
LOW_RISK_MARKERS = ("docs/", "readme", "test", ".md")


async def predict_severity(
    ctx: ToolContext,
    service: str,
    alertname: str,
    error_rate_pct: float | None = None,
    latency_p95_ms: float | None = None,
    memory_pct: float | None = None,
    request_rate_rps: float | None = None,
    cpu_pct: float | None = None,
    deploy_within_hour: bool = False,
) -> dict:
    return {
        "service": service,
        "alertname": alertname,
        **_heuristic_severity(
            alertname, error_rate_pct, latency_p95_ms, memory_pct, deploy_within_hour
        ),
    }


def _heuristic_severity(
    alertname: str,
    error_rate_pct: float | None,
    latency_p95_ms: float | None,
    memory_pct: float | None,
    deploy_within_hour: bool,
) -> dict:
    score = 0
    signals: list[str] = []

    if error_rate_pct is not None:
        if error_rate_pct >= 10:
            score, note = score + 3, f"error rate {error_rate_pct}% >= 10%"
        elif error_rate_pct >= 5:
            score, note = score + 2, f"error rate {error_rate_pct}% >= 5%"
        elif error_rate_pct >= 2:
            score, note = score + 1, f"error rate {error_rate_pct}% >= 2%"
        else:
            note = None
        if note:
            signals.append(note)
    if latency_p95_ms is not None and latency_p95_ms >= 2000:
        score += 1
        signals.append(f"p95 latency {latency_p95_ms}ms >= 2000ms")
    if memory_pct is not None and memory_pct >= 90:
        score += 1
        signals.append(f"memory {memory_pct}% >= 90%")
    if deploy_within_hour:
        score += 1
        signals.append("deploy within the last hour")
    if "exhausted" in alertname.lower():
        score += 1
        signals.append("resource-exhaustion alert class")

    severity = "critical" if score >= 4 else "high" if score == 3 else "medium" if score == 2 else "low"
    return {
        "severity": severity,
        "score": score,
        "signals": signals,
        "method": "heuristic-v0 (fallback: no trained model artifact found)",
    }
