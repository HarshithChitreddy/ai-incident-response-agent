"""Slack integration: deterministic Block Kit builders + a dual-transport sender.

Messages are built from the structured analysis fields (not the LLM's free-text
brief) so the format is guaranteed and testable — the LLM supplies content, the
template supplies structure. The sender always persists the message to Postgres
(mock transport / audit log / dashboard feed) and additionally POSTs to a real
Slack incoming webhook when SLACK_WEBHOOK_URL is configured. Webhook failures
are recorded on the row, never raised — notifications must not fail agent runs.
"""

import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Incident, SlackMessage

logger = logging.getLogger(__name__)

SEVERITY_EMOJI = {
    "critical": ":rotating_light:",
    "high": ":red_circle:",
    "medium": ":large_orange_circle:",
    "low": ":large_yellow_circle:",
    "warning": ":warning:",
}

# Slack Block Kit hard limits
_HEADER_MAX = 150
_SECTION_MAX = 3000
_CONTEXT_MAX = 2000


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _mrkdwn(text: str, limit: int = _SECTION_MAX) -> dict[str, Any]:
    return {"type": "mrkdwn", "text": _clip(text, limit)}


def build_incident_opened_message(incident: Incident, analysis: dict[str, Any]) -> dict[str, Any]:
    severity = str(analysis.get("severity") or incident.severity or "warning")
    emoji = SEVERITY_EMOJI.get(severity, ":warning:")
    confidence = analysis.get("confidence")
    confidence_txt = (
        f"{round(confidence * 100)}%" if isinstance(confidence, (int, float)) else "n/a"
    )
    root_cause = analysis.get("root_cause") or "Investigation in progress."

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": _clip(f"{emoji} [{severity.upper()}] {incident.alertname} — {incident.service}", _HEADER_MAX),
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                _mrkdwn(f"*Service:*\n{incident.service}"),
                _mrkdwn(f"*Severity:*\n{severity}"),
                _mrkdwn(f"*Status:*\n{incident.status}"),
                _mrkdwn(f"*Started:*\n{incident.started_at:%Y-%m-%d %H:%M} UTC"),
                _mrkdwn(f"*Confidence:*\n{confidence_txt}"),
                _mrkdwn(f"*Alert:*\n{incident.alertname}"),
            ],
        },
        {"type": "section", "text": _mrkdwn(f"*Likely cause*\n{root_cause}")},
    ]

    if analysis.get("user_impact"):
        blocks.append({"type": "section", "text": _mrkdwn(f"*Impact*\n{analysis['user_impact']}")})

    steps = analysis.get("recommended_runbook_steps") or []
    if steps:
        bullets = "\n".join(f"• {s}" for s in steps[:3])
        blocks.append({"type": "section", "text": _mrkdwn(f"*Next steps*\n{bullets}")})

    context_bits = [f"AI triage · incident `{incident.id}`"]
    if analysis.get("why_it_might_be_wrong"):
        context_bits.append(f"Caveat: {analysis['why_it_might_be_wrong']}")
    blocks.append(
        {
            "type": "context",
            "elements": [_mrkdwn(bit, _CONTEXT_MAX) for bit in context_bits],
        }
    )

    fallback = _clip(
        f"[{severity.upper()}] {incident.alertname} on {incident.service}: {root_cause}", 300
    )
    return {"channel": "#incidents", "text": fallback, "blocks": blocks}
