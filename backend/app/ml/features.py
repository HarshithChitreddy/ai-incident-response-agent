"""Shared feature definitions for the severity model — one source of truth for
training, inference, and the tool schema."""

SEVERITIES = ["low", "medium", "high", "critical"]

ALERTNAMES = [
    "HighErrorRate",
    "HighLatencyP95",
    "DBConnectionPoolExhausted",
    "HighMemoryUsage",
]

NUMERIC_FEATURES = [
    "error_rate_pct",
    "latency_p95_ms",
    "request_rate_rps",
    "cpu_pct",
    "memory_pct",
    "deploy_within_hour",
]

FEATURES = ["alertname", *NUMERIC_FEATURES]
