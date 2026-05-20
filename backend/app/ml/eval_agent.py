"""Agent root-cause attribution eval.

    python -m app.ml.eval_agent [--skip-agent] [--limit N]

Each case in data/eval_incidents.json is a self-contained evidence world with a
known culprit commit. The harness materializes the world into a temp data dir,
then scores two levels:

- ranker top-1: does rank_likely_commits put the culprit first? (deterministic)
- agent top-1: does the full triage agent's analysis name the culprit? With
  MOCK_LLM the mock grounds its verdict in the ranker's tool output, so this
  measures the evidence pipeline; with MOCK_LLM=false it measures real
  end-to-end reasoning — that's the headline number.

The report is written to MODEL_DIR/agent_eval.json.
"""

import argparse
import asyncio
import csv
import io
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agents.runner import run_triage_for_incident
from app.config import Settings, get_settings
from app.models import AgentRun, Base, HistoricalIncident, Incident
from app.services.llm import LLMClient, get_llm_client
from app.tools.base import ToolContext
from app.tools.heuristics import rank_likely_commits

METRIC_DEFAULTS = {
    "error_rate_pct": 0.3,
    "latency_p95_ms": 300,
    "request_rate_rps": 100,
    "cpu_pct": 45,
    "memory_pct": 60,
}


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _commit_entry(spec: dict, service: str, started: datetime) -> dict:
    return {
        "sha": spec["sha"],
        "service": service,
        "author": spec.get("author", "dev"),
        "timestamp": _iso(started - timedelta(hours=spec["hours_before"])),
        "message": spec["message"],
        "files": spec.get("files", []),
        "additions": spec.get("additions", 24),
        "deletions": spec.get("deletions", 6),
        "diff_summary": spec.get("diff_summary", ""),
    }


def write_case_world(case: dict, benign_pool: list[dict], dest: Path) -> None:
    """Materialize one eval case as the data files the agent tools read."""
    dest.mkdir(parents=True, exist_ok=True)
    started = _parse_ts(case["started_at"])
    service = case["service"]

    commits = [_commit_entry(c, service, started) for c in case["case_commits"]]
    for entry in benign_pool:
        entry_service = service if entry.get("service") == "SERVICE" else entry.get("service", "platform")
        commits.append(_commit_entry(entry, entry_service, started))
    (dest / "sample_commits.json").write_text(json.dumps(commits, indent=1))

    logs = []
    case_logs = case.get("logs", [])
    for i, entry in enumerate(case_logs):
        logs.append(
            {
                "timestamp": _iso(started - timedelta(minutes=5 * (len(case_logs) - i))),
                "service": service,
                "level": entry.get("level", "ERROR"),
                "logger": "app",
                "trace_id": None,
                "message": entry["message"],
            }
        )
    (dest / "sample_logs.json").write_text(json.dumps(logs, indent=1))

    anomaly = case["anomaly"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["timestamp", "service", *METRIC_DEFAULTS])
    writer.writeheader()
    for i in range(8):
        row = {
            "timestamp": _iso(started - timedelta(minutes=10 * (7 - i))),
            "service": service,
            **METRIC_DEFAULTS,
        }
        if i >= 4:  # ramp the anomalous metric over the last four points
            fraction = (i - 3) / 4
            row[anomaly["metric"]] = round(
                anomaly["baseline"] + (anomaly["peak"] - anomaly["baseline"]) * fraction, 2
            )
        else:
            row[anomaly["metric"]] = anomaly["baseline"]
        writer.writerow(row)
    (dest / "sample_metrics.csv").write_text(buf.getvalue())


async def _seed_history(factory, csv_path: Path) -> None:
    if not csv_path.exists():
        return
    async with factory() as db:
        with csv_path.open(newline="") as f:
            rows = [
                HistoricalIncident(
                    service=r["service"], alertname=r["alertname"], severity=r["severity"],
                    error_rate_pct=float(r["error_rate_pct"]), latency_p95_ms=float(r["latency_p95_ms"]),
                    request_rate_rps=float(r["request_rate_rps"]), cpu_pct=float(r["cpu_pct"]),
                    memory_pct=float(r["memory_pct"]), deploy_within_hour=r["deploy_within_hour"] == "1",
                    root_cause=r["root_cause"], time_to_resolve_min=int(r["time_to_resolve_min"]),
                    summary=r["summary"],
                )
                for r in csv.DictReader(f)
            ]
        db.add_all(rows)
        await db.commit()
