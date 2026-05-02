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
