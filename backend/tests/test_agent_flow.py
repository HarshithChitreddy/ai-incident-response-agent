"""End-to-end agent flow tests with the mock LLM: webhook -> triage run ->
analysis + trace + Slack brief; resolve -> postmortem. Background tasks run
against the test database via the get_session_factory override, so these
exercise the exact production wiring."""

from sqlalchemy import func, select

from app.agents.runner import run_triage_for_incident
from app.models import AgentRun, Incident, TraceStep, utcnow
from app.services.llm import MockLLMClient
from app.tools.registry import TOOLS
from tests.factories import make_alert, make_webhook

WEBHOOK_URL = "/api/v1/alerts/webhook"

EXPECTED_TOOL_NAMES = [t.name for t in TOOLS]


async def _create_incident(client) -> str:
    resp = await client.post(
        WEBHOOK_URL, json=make_webhook(alerts=[make_alert(service="checkout-service")])
    )
    return resp.json()["created"][0]


async def test_triage_run_produces_analysis_trace_and_brief(client, session_factory):
    # client fixture wires background tasks to the test db, so the webhook
    # already ran a full triage by the time it returns
    incident_id = await _create_incident(client)

    analysis_resp = await client.get(f"/api/v1/incidents/{incident_id}/analysis")
    assert analysis_resp.status_code == 200
    body = analysis_resp.json()
    analysis = body["analysis"]

    assert analysis["root_cause"]
    assert analysis["why_it_might_be_wrong"]
    assert 0 <= analysis["confidence"] <= 1
    assert len(analysis["competing_candidates"]) >= 2
    assert "CRITICAL" in analysis["slack_brief"]

    # the model's predicted severity was written back to the incident
    incident = (await client.get(f"/api/v1/incidents/{incident_id}")).json()
    assert incident["severity"] == analysis["severity"] == "critical"


async def test_trace_records_every_llm_and_tool_step(client):
    incident_id = await _create_incident(client)

    steps = (await client.get(f"/api/v1/incidents/{incident_id}/trace")).json()
    assert steps

    seqs = [s["seq"] for s in steps]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)

    tool_steps = [s["name"] for s in steps if s["step_type"] == "tool_call"]
    assert tool_steps == EXPECTED_TOOL_NAMES  # mock calls each tool once, in order

    llm_steps = [s for s in steps if s["step_type"] == "llm_call"]
    # one llm call per tool round + the final answer + the slack brief
    assert len(llm_steps) == len(EXPECTED_TOOL_NAMES) + 2
    assert steps[0]["step_type"] == "llm_call"
    assert llm_steps[-1]["name"] == "generate_slack_brief"
    assert all(s["tokens_in"] > 0 for s in llm_steps)

    # tool inputs/outputs are stored verbatim for the dashboard
    commits_step = next(s for s in steps if s["name"] == "get_recent_commits")
    assert commits_step["input"]["service"] == "checkout-service"


async def test_resolve_generates_postmortem_once(client):
    incident_id = await _create_incident(client)

    await client.post(f"/api/v1/incidents/{incident_id}/resolve")
    pm = await client.get(f"/api/v1/incidents/{incident_id}/postmortem")
    assert pm.status_code == 200
    assert pm.json()["markdown"].startswith("# Postmortem")

    # resolving again must not create a second postmortem
    await client.post(f"/api/v1/incidents/{incident_id}/resolve")
    runs = (await client.get(f"/api/v1/incidents/{incident_id}/runs")).json()
    postmortems = [r for r in runs if r["kind"] == "postmortem" and r["status"] == "completed"]
    assert len(postmortems) == 1


async def test_webhook_resolved_alert_also_triggers_postmortem(client):
    incident_id = await _create_incident(client)

    resolved = make_webhook(
        alerts=[make_alert(status="resolved", ends_at="2026-07-07T15:00:00Z")],
        status="resolved",
    )
    await client.post(WEBHOOK_URL, json=resolved)

    pm = await client.get(f"/api/v1/incidents/{incident_id}/postmortem")
    assert pm.status_code == 200
    assert "## Root Cause" in pm.json()["markdown"]
