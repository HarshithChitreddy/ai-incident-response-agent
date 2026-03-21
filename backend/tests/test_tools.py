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
