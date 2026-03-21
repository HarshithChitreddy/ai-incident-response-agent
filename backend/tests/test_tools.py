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
