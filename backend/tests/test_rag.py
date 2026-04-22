"""Retrieval-relevance tests for the runbook RAG layer.

These run real MiniLM embeddings (local ONNX model, cached after first
download) — they assert actual semantic retrieval quality, not mocks.
"""

import pytest

from app.config import get_settings
from app.rag.store import RunbookIndex
from app.tools.base import ToolContext
from app.tools.evidence import retrieve_runbook

# (query the agent would compose from alert + logs, expected runbook)
RELEVANCE_CASES = [
    (
        "HighErrorRate: 5xx error rate above threshold, payment authorization "
        "timeouts on POST /api/checkout/confirm",
        "high-error-rate.md",
    ),
    (
        "DBConnectionPoolExhausted: zero idle database connections, requests "
        "queueing and timing out waiting for a connection",
        "db-connection-pool.md",
    ),
    (
        "HighMemoryUsage: container memory climbing steadily over hours with flat "
        "traffic, GC pauses increasing, OOM kill likely",
        "memory-leak.md",
    ),
    (
        "HighLatencyP95: p95 latency 2400ms over SLO, slow Elasticsearch queries, "
        "error rate still low",
        "high-latency.md",
    ),
    (
        "procedure to roll back a bad deploy with kubectl rollout undo",
        "deploy-rollback.md",
    ),
]


@pytest.mark.parametrize(("query", "expected"), RELEVANCE_CASES)
async def test_top_hit_matches_alert_class(runbook_index, query, expected):
    chunks = await runbook_index.search(query, k=3)
    assert chunks, "no results returned"
    assert chunks[0].source == expected, (
        f"expected {expected}, got {[c.source for c in chunks]}"
    )


async def test_retrieval_from_alert_plus_raw_log_lines(runbook_index):
    """The agent builds queries from the alert plus log excerpts — retrieval
    must survive that noisier input."""
    query = (
        "HighErrorRate on checkout-service. Logs: "
        "PaymentGatewayTimeout: authorize() exceeded 2000ms deadline (attempt 3/3), giving up; "
        "POST /api/checkout/confirm -> 502 payment authorization failed after retries"
    )
    chunks = await runbook_index.search(query, k=3)
    assert chunks[0].source == "high-error-rate.md"


async def test_scores_are_bounded_and_descending(runbook_index):
    chunks = await runbook_index.search("database connection pool exhausted", k=4)
    scores = [c.score for c in chunks]
    assert all(s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)
    assert all(c.section for c in chunks)  # section metadata survives round-trip


async def test_persisted_index_is_reused_across_instances(tmp_path):
    runbooks = tmp_path / "runbooks"
    runbooks.mkdir()
    (runbooks / "disk.md").write_text(
        "# Disk Full Runbook\n## Symptoms\nDisk usage above 95 percent, writes failing."
    )
    persist = tmp_path / "chroma"

    first = RunbookIndex(persist_dir=persist, runbooks_dir=runbooks)
    first.ensure_indexed()

    second = RunbookIndex(persist_dir=persist, runbooks_dir=runbooks)
    second.ensure_indexed()

    # same collection id means the fingerprint matched and no rebuild happened
    assert second.collection_id == first.collection_id
