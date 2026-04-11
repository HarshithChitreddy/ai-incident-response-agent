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
