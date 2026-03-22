"""Unit tests for each agent tool, run against the real data/ files and a
seeded test database."""

import pytest

from app.config import get_settings
from app.models import HistoricalIncident
from app.tools.base import ToolContext
from app.tools.evidence import (
    find_similar_incidents,
    get_recent_commits,
    query_metrics,
    retrieve_runbook,
    search_logs,
)
from app.tools.heuristics import predict_severity, rank_likely_commits
from app.tools.registry import anthropic_tool_defs, dispatch


@pytest.fixture
async def ctx(session_factory):
    async with session_factory() as db:
        yield ToolContext(db=db, settings=get_settings())


@pytest.fixture
async def seeded_history(session_factory):
    rows = [
        HistoricalIncident(
            service="checkout-service", alertname="HighErrorRate", severity="critical",
            error_rate_pct=13.5, latency_p95_ms=2300, request_rate_rps=148, cpu_pct=74,
            memory_pct=63, deploy_within_hour=True, root_cause="bad_deploy",
            time_to_resolve_min=44, summary="Tightened timeout below upstream p50 triggered retry storm",
        ),
        HistoricalIncident(
            service="orders-service", alertname="DBConnectionPoolExhausted", severity="critical",
            error_rate_pct=6.5, latency_p95_ms=9000, request_rate_rps=64, cpu_pct=40,
            memory_pct=54, deploy_within_hour=True, root_cause="config_change",
            time_to_resolve_min=38, summary="Pool size lowered during cost cleanup",
        ),
        HistoricalIncident(
            service="search-service", alertname="HighLatencyP95", severity="warning",
            error_rate_pct=0.9, latency_p95_ms=2200, request_rate_rps=215, cpu_pct=66,
            memory_pct=67, deploy_within_hour=True, root_cause="bad_deploy",
            time_to_resolve_min=35, summary="Query expansion multiplied ES clause count",
        ),
    ]
    async with session_factory() as db:
        db.add_all(rows)
        await db.commit()


async def test_get_recent_commits_filters_and_sorts(ctx):
    commits = await get_recent_commits(ctx, service="checkout-service")

    services = {c["service"] for c in commits}
    assert services <= {"checkout-service", "platform"}
    assert "checkout-service" in services
    timestamps = [c["timestamp"] for c in commits]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_search_logs_by_query_and_level(ctx):
    errors = await search_logs(ctx, service="checkout-service", level="ERROR")
    assert errors and all(e["level"] == "ERROR" for e in errors)

    timeouts = await search_logs(ctx, service="checkout-service", query="PaymentGatewayTimeout")
    assert timeouts and all("PaymentGatewayTimeout" in e["message"] for e in timeouts)

    nothing = await search_logs(ctx, service="checkout-service", query="zzz-no-match")
    assert nothing == []


async def test_query_metrics_summarizes_regression(ctx):
    result = await query_metrics(ctx, service="checkout-service")

    assert result["series"]
    err = result["summary"]["error_rate_pct"]
    assert err["current"] > err["baseline"]  # the seeded story: error rate ramps up
    assert err["delta_pct"] > 100

    empty = await query_metrics(ctx, service="ghost-service")
    assert empty["series"] == []


async def test_retrieve_runbook_matches_alert_class(ctx):
    # ctx has no injected index, so this exercises the shared accessor path
    # (routed to the session test index by conftest)
    result = await retrieve_runbook(ctx, query="HighErrorRate 5xx payment timeouts")
    assert result["runbook"] == "high-error-rate.md"
    assert result["retriever"] == "chroma/all-MiniLM-L6-v2"
    assert "roll back" in result["content"].lower()

    pool = await retrieve_runbook(ctx, query="DBConnectionPoolExhausted idle connections")
    assert pool["runbook"] == "db-connection-pool.md"


async def test_find_similar_incidents_prefers_same_alertname(ctx, seeded_history):
    results = await find_similar_incidents(
        ctx, service="checkout-service", alertname="HighErrorRate"
    )
    assert results
    assert results[0]["alertname"] == "HighErrorRate"
    assert results[0]["root_cause"] == "bad_deploy"


async def test_predict_severity_heuristic_bounds(ctx):
    critical = await predict_severity(
        ctx, service="checkout-service", alertname="HighErrorRate",
        error_rate_pct=12.4, latency_p95_ms=2190, deploy_within_hour=True,
    )
    assert critical["severity"] == "critical"
    assert critical["signals"]

    low = await predict_severity(ctx, service="search-service", alertname="HighLatencyP95")
    assert low["severity"] == "low"


async def test_rank_likely_commits_finds_the_planted_culprit(ctx):
    ranked = await rank_likely_commits(
        ctx, service="checkout-service", incident_started_at="2026-07-07T14:02:00Z"
    )
    assert ranked[0]["sha"] == "9f2c41ab7e03"  # the timeout+retry commit
    assert ranked[0]["score"] > ranked[-1]["score"]


async def test_rank_likely_commits_tolerates_bad_timestamp(ctx):
    ranked = await rank_likely_commits(
        ctx, service="checkout-service", incident_started_at="not-a-date"
    )
    assert ranked  # falls back to newest-commit reference instead of crashing
