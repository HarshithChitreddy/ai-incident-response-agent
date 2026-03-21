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
