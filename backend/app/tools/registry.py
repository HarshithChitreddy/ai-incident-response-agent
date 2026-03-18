"""The agent's tool surface: Anthropic-format definitions plus dispatch.

Descriptions are prescriptive about *when* to call each tool — that's what the
model keys on when deciding tool use.
"""

from typing import Any

from app.tools.base import ToolContext, ToolSpec
from app.tools.evidence import (
    find_similar_incidents,
    get_recent_commits,
    query_metrics,
    retrieve_runbook,
    search_logs,
)
from app.tools.heuristics import predict_severity, rank_likely_commits

TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_recent_commits",
        description=(
            "List recent commits for a service (plus shared platform commits). Call this "
            "first for any incident — a recent deploy is the most common root cause."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name, e.g. checkout-service"},
                "limit": {"type": "integer", "description": "Max commits to return"},
            },
            "required": ["service"],
        },
        handler=get_recent_commits,
    ),
    ToolSpec(
        name="search_logs",
        description=(
            "Search application logs for a service. Call this to find the concrete error "
            "messages behind an alert; filter by level=ERROR to see failures only."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "query": {"type": "string", "description": "Case-insensitive substring filter"},
                "level": {"type": "string", "enum": ["ERROR", "WARNING", "INFO"]},
                "limit": {"type": "integer"},
            },
            "required": ["service"],
        },
        handler=search_logs,
    ),
    ToolSpec(
        name="query_metrics",
        description=(
            "Fetch the recent metric series (error rate, p95 latency, request rate, CPU, "
            "memory) for a service with baseline-vs-current deltas. Call this to see when "
            "the regression started and how it is trending."
        ),
        input_schema={
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
        handler=query_metrics,
    ),
    ToolSpec(
        name="retrieve_runbook",
        description=(
            "Semantic search over the operational runbook library. Call this with the "
            "alert name, the symptoms, and one or two representative log lines — richer "
            "queries retrieve the right triage and mitigation sections more reliably."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Alert name + symptoms + key log lines, e.g. 'HighErrorRate 5xx "
                        "payment authorization timeout retry storm'"
                    ),
                }
            },
            "required": ["query"],
        },
        handler=retrieve_runbook,
    ),
    ToolSpec(
        name="find_similar_incidents",
        description=(
            "Look up past incidents with the same alert class or service, including their "
            "confirmed root causes and time-to-resolve. Call this to check what caused "
            "identical incidents before."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "alertname": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["service"],
        },
        handler=find_similar_incidents,
    ),
    ToolSpec(
        name="predict_severity",
        description=(
            "Predict incident severity from observed signals. Call this after checking "
            "metrics, passing the current error rate / latency / memory values you found."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "alertname": {"type": "string"},
                "error_rate_pct": {"type": "number"},
                "latency_p95_ms": {"type": "number"},
                "memory_pct": {"type": "number"},
                "request_rate_rps": {"type": "number"},
                "cpu_pct": {"type": "number"},
                "deploy_within_hour": {"type": "boolean"},
            },
            "required": ["service", "alertname"],
        },
        handler=predict_severity,
    ),
    ToolSpec(
        name="rank_likely_commits",
        description=(
            "Rank the service's recent commits by likelihood of causing the incident "
            "(recency, blast radius, risky change markers). Call this after reviewing "
            "commits and logs to cross-check your own suspicion."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "incident_started_at": {
                    "type": "string",
                    "description": "ISO-8601 incident start time, from the alert",
                },
            },
            "required": ["service"],
        },
        handler=rank_likely_commits,
    ),
]

_BY_NAME = {spec.name: spec for spec in TOOLS}


def anthropic_tool_defs() -> list[dict[str, Any]]:
    return [spec.to_anthropic() for spec in TOOLS]


async def dispatch(ctx: ToolContext, name: str, tool_input: dict[str, Any]) -> Any:
    spec = _BY_NAME.get(name)
    if spec is None:
        raise KeyError(f"unknown tool: {name}")
    return await spec.handler(ctx, **tool_input)
