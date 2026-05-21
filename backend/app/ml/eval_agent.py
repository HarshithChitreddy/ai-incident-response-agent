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


async def run_eval(
    cases_path: Path | str | None = None,
    limit: int | None = None,
    use_agent: bool = True,
    llm: LLMClient | None = None,
) -> dict:
    settings = get_settings()
    cases_path = Path(cases_path or settings.data_dir / "eval_incidents.json")
    spec = json.loads(cases_path.read_text())
    cases = spec["cases"][:limit] if limit else spec["cases"]
    benign_pool = spec.get("benign_commit_pool", [])

    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await _seed_history(factory, settings.data_dir / "historical_incidents.csv")

    llm = llm or get_llm_client()
    results: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="agent-eval-") as tmp_str:
        tmp = Path(tmp_str)
        shared_index = None
        if use_agent:
            from app.rag.store import RunbookIndex

            shared_index = RunbookIndex(
                persist_dir=tmp / "chroma", runbooks_dir=settings.data_dir / "runbooks"
            )

        for case in cases:
            case_dir = tmp / case["id"]
            write_case_world(case, benign_pool, case_dir)
            case_settings = Settings(
                _env_file=None,
                data_dir=case_dir,
                model_dir=settings.model_dir,
                mock_llm=settings.mock_llm,
            )
            expected = case["expected_commit"]

            async with factory() as db:
                incident = Incident(
                    fingerprint=case["id"],
                    alertname=case["alertname"],
                    service=case["service"],
                    severity=case["severity"],
                    status="open",
                    title=case["title"],
                    description=case.get("description", ""),
                    labels={
                        "alertname": case["alertname"],
                        "service": case["service"],
                        "severity": case["severity"],
                    },
                    annotations={},
                    started_at=_parse_ts(case["started_at"]),
                )
                db.add(incident)
                await db.commit()
                await db.refresh(incident)
                incident_id = incident.id

                ranked = await rank_likely_commits(
                    ToolContext(db=db, settings=case_settings),
                    service=case["service"],
                    incident_started_at=case["started_at"],
                )

            ranker_top = ranked[0]["sha"] if ranked else None
            row = {
                "case": case["id"],
                "service": case["service"],
                "alertname": case["alertname"],
                "expected": expected,
                "ranker_top": ranker_top,
                "ranker_correct": ranker_top == expected,
            }

            if use_agent:
                await run_triage_for_incident(
                    incident_id,
                    session_factory=factory,
                    llm=llm,
                    settings=case_settings,
                    runbook_index=shared_index,
                )
                async with factory() as db:
                    run = await db.scalar(
                        select(AgentRun)
                        .where(AgentRun.incident_id == incident_id, AgentRun.kind == "triage")
                        .order_by(AgentRun.started_at.desc())
                        .limit(1)
                    )
                analysis = run.result if run is not None and run.status == "completed" else {}
                candidates = analysis.get("competing_candidates") or []
                agent_top = str(candidates[0].get("commit", "")) if candidates else ""
                row |= {
                    "run_status": run.status if run is not None else "missing",
                    "agent_top": agent_top,
                    "agent_correct": expected in agent_top
                    or expected in str(analysis.get("root_cause", "")),
                    "agent_recall": expected in json.dumps(analysis),
                }

            results.append(row)

    await engine.dispose()

    total = len(results)
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "llm": getattr(llm, "model", "unknown"),
        "cases": total,
        "ranker": _summary(results, "ranker_correct", total),
        "per_case": results,
    }
    if use_agent:
        report["agent"] = _summary(results, "agent_correct", total)
        report["agent"]["candidate_recall"] = round(
            sum(r.get("agent_recall", False) for r in results) / total, 3
        )
    return report


def _summary(results: list[dict], key: str, total: int) -> dict:
    correct = sum(r.get(key, False) for r in results)
    return {"correct": correct, "total": total, "top1_accuracy": round(correct / total, 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-agent", action="store_true", help="score the ranker only")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cases", default=None)
    args = parser.parse_args()

    report = asyncio.run(
        run_eval(cases_path=args.cases, limit=args.limit, use_agent=not args.skip_agent)
    )

    print(f"llm={report['llm']}  cases={report['cases']}")
    header = f"{'case':<9}{'expected':<15}{'ranker_top':<15}{'r✓':<4}"
    if "agent" in report:
        header += f"{'agent_top':<15}{'a✓':<4}"
    print(header)
    for row in report["per_case"]:
        line = f"{row['case']:<9}{row['expected']:<15}{str(row['ranker_top']):<15}{'Y' if row['ranker_correct'] else '.':<4}"
        if "agent" in report:
            line += f"{row.get('agent_top', ''):<15}{'Y' if row.get('agent_correct') else '.':<4}"
        print(line)
    print(f"\nranker top-1 accuracy: {report['ranker']['top1_accuracy']} ({report['ranker']['correct']}/{report['ranker']['total']})")
    if "agent" in report:
        mode = " [MOCK LLM — evidence-pipeline score; run with MOCK_LLM=false for the real number]" if get_settings().mock_llm else ""
        print(f"agent  top-1 accuracy: {report['agent']['top1_accuracy']} ({report['agent']['correct']}/{report['agent']['total']}){mode}")
        print(f"agent  candidate recall: {report['agent']['candidate_recall']}")

    out = Path(get_settings().model_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "agent_eval.json").write_text(json.dumps(report, indent=2))
    print(f"\nreport saved to {out / 'agent_eval.json'}")


if __name__ == "__main__":
    main()
