"""Slack message formatting and delivery tests: Block Kit structure, limit
handling, mock vs webhook transport, and the end-to-end incident feed."""

from datetime import datetime, timedelta, timezone

import httpx

from app.config import Settings
from app.models import Incident
from app.services.slack import (
    SlackService,
    build_incident_opened_message,
    build_incident_resolved_message,
)
from tests.factories import make_webhook

WEBHOOK_URL = "/api/v1/alerts/webhook"

STARTED = datetime(2026, 7, 7, 14, 2, tzinfo=timezone.utc)

ANALYSIS = {
    "root_cause": "Commit 9f2c41ab7e03 tightened the payment gateway timeout below upstream p50.",
    "why_it_might_be_wrong": "The gateway's own latency rose in the same window.",
    "confidence": 0.72,
    "severity": "critical",
    "user_impact": "~19 failed orders/min at current traffic.",
    "recommended_runbook_steps": [
        "Roll back to the previous release.",
        "Disable the no-backoff retry wrapper.",
        "Verify error rate stays under 1% for 15 minutes.",
        "A fourth step that should be dropped from the message.",
    ],
}


def make_incident(**overrides) -> Incident:
    defaults = dict(
        fingerprint="fp-test",
        alertname="HighErrorRate",
        service="checkout-service",
        severity="critical",
        status="open",
        title="checkout-service error rate at 12.4% (threshold 2%)",
        description="5xx error rate above 2% for 5 minutes.",
        labels={},
        annotations={},
        started_at=STARTED,
    )
    return Incident(**{**defaults, **overrides})


def _sections_text(message: dict) -> str:
    parts = []
    for block in message["blocks"]:
        if block["type"] == "section" and "text" in block:
            parts.append(block["text"]["text"])
        for el in block.get("elements", []):
            parts.append(el["text"])
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #


def test_opened_message_structure():
    msg = build_incident_opened_message(make_incident(), ANALYSIS)

    header = msg["blocks"][0]
    assert header["type"] == "header"
    assert "[CRITICAL]" in header["text"]["text"]
    assert "HighErrorRate" in header["text"]["text"]
    assert ":rotating_light:" in header["text"]["text"]
    assert len(header["text"]["text"]) <= 150

    fields = msg["blocks"][1]["fields"]
    field_text = "\n".join(f["text"] for f in fields)
    assert "*Service:*\ncheckout-service" in field_text
    assert "*Confidence:*\n72%" in field_text
    assert "*Started:*\n2026-07-07 14:02 UTC" in field_text

    body = _sections_text(msg)
    assert "Commit 9f2c41ab7e03" in body
    assert "*Impact*" in body
    assert "Caveat:" in body

    # notification fallback text carries the essentials
    assert "HighErrorRate" in msg["text"]
    assert "checkout-service" in msg["text"]


def test_opened_message_limits_steps_to_three_bullets():
    msg = build_incident_opened_message(make_incident(), ANALYSIS)
    steps_block = next(
        b for b in msg["blocks"]
        if b["type"] == "section" and "Next steps" in b.get("text", {}).get("text", "")
    )
    bullets = [line for line in steps_block["text"]["text"].splitlines() if line.startswith("•")]
    assert len(bullets) == 3
    assert "fourth step" not in steps_block["text"]["text"]


def test_opened_message_survives_empty_analysis():
    msg = build_incident_opened_message(make_incident(), {})

    assert msg["blocks"][0]["type"] == "header"
    assert "Investigation in progress." in _sections_text(msg)
    fields = "\n".join(f["text"] for f in msg["blocks"][1]["fields"])
    assert "*Confidence:*\nn/a" in fields
    # no impact/steps blocks, and nothing crashed
    assert all("Next steps" not in str(b) for b in msg["blocks"])


def test_long_root_cause_is_truncated_to_slack_limit():
    huge = {"root_cause": "x" * 5000, "severity": "critical"}
    msg = build_incident_opened_message(make_incident(), huge)
    cause_block = next(
        b for b in msg["blocks"]
        if b["type"] == "section" and "Likely cause" in b.get("text", {}).get("text", "")
    )
    text = cause_block["text"]["text"]
    assert len(text) <= 3000
    assert text.endswith("…")


def test_resolved_message_reports_duration_and_postmortem():
    incident = make_incident(
        status="resolved", resolved_at=STARTED + timedelta(minutes=72)
    )
    msg = build_incident_resolved_message(incident, postmortem_ready=True)

    assert ":white_check_mark:" in msg["blocks"][0]["text"]["text"]
    body = _sections_text(msg)
    assert "*Duration:* 1h 12m" in body
    assert "postmortem" in body.lower()
    assert "1h 12m" in msg["text"]


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #


async def _persisted_incident(session_factory) -> Incident:
    async with session_factory() as db:
        incident = make_incident()
        db.add(incident)
        await db.commit()
        await db.refresh(incident)
        return incident


async def test_mock_transport_stores_message(session_factory):
    incident = await _persisted_incident(session_factory)
    async with session_factory() as db:
        service = SlackService(db, Settings(_env_file=None))  # no webhook URL
        row = await service.post(
            incident.id, "incident_opened", build_incident_opened_message(incident, ANALYSIS)
        )

    assert row.transport == "mock"
    assert row.delivered is True
    assert row.blocks[0]["type"] == "header"  # blocks survive the JSON round-trip


async def test_webhook_transport_delivers(session_factory):
    incident = await _persisted_incident(session_factory)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, text="ok")

    settings = Settings(_env_file=None, slack_webhook_url="https://hooks.slack.example/services/T/B/x")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with session_factory() as db:
        service = SlackService(db, settings, client=client)
        row = await service.post(
            incident.id, "incident_opened", build_incident_opened_message(incident, ANALYSIS)
        )

    assert row.transport == "slack_webhook"
    assert row.delivered is True
    assert seen["payload"]["blocks"][0]["type"] == "header"
    assert seen["payload"]["text"]


async def test_webhook_failure_is_recorded_not_raised(session_factory):
    incident = await _persisted_incident(session_factory)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream sad")

    settings = Settings(_env_file=None, slack_webhook_url="https://hooks.slack.example/services/T/B/x")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with session_factory() as db:
        service = SlackService(db, settings, client=client)
        row = await service.post(
            incident.id, "incident_opened", build_incident_opened_message(incident, ANALYSIS)
        )

    assert row.delivered is False
    assert "500" in row.delivery_error
    # the message is still stored for the dashboard despite failed delivery
    assert row.blocks


# --------------------------------------------------------------------------- #
# End-to-end feed
# --------------------------------------------------------------------------- #


async def test_incident_lifecycle_posts_opened_then_resolved(client):
    created = (await client.post(WEBHOOK_URL, json=make_webhook())).json()["created"]
    incident_id = created[0]

    feed = (await client.get(f"/api/v1/incidents/{incident_id}/slack")).json()
    assert [m["kind"] for m in feed] == ["incident_opened"]
    assert feed[0]["transport"] == "mock"
    assert "HighErrorRate" in feed[0]["blocks"][0]["text"]["text"]

    await client.post(f"/api/v1/incidents/{incident_id}/resolve")
    feed = (await client.get(f"/api/v1/incidents/{incident_id}/slack")).json()
    assert [m["kind"] for m in feed] == ["incident_opened", "incident_resolved"]
    assert "Resolved" in feed[1]["blocks"][0]["text"]["text"]

    # the notification itself appears in the agent trace
    steps = (await client.get(f"/api/v1/incidents/{incident_id}/trace")).json()
    assert any(s["step_type"] == "notification" for s in steps)
