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


def _fmt_duration(start: datetime, end: datetime) -> str:
    minutes = max(0, int((end - start).total_seconds() // 60))
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m" if hours else f"{mins}m"


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


def build_incident_resolved_message(
    incident: Incident, postmortem_ready: bool = False
) -> dict[str, Any]:
    resolved_at = incident.resolved_at or incident.started_at
    duration = _fmt_duration(incident.started_at, resolved_at)

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": _clip(f":white_check_mark: Resolved: {incident.alertname} — {incident.service}", _HEADER_MAX),
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": _mrkdwn(
                f"*{incident.title}* is resolved.\n"
                f"*Duration:* {duration} · *Severity:* {incident.severity}"
            ),
        },
    ]
    if postmortem_ready:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    _mrkdwn(
                        f"Postmortem ready: `GET /api/v1/incidents/{incident.id}/postmortem`",
                        _CONTEXT_MAX,
                    )
                ],
            }
        )

    fallback = f"Resolved: {incident.alertname} on {incident.service} after {duration}"
    return {"channel": "#incidents", "text": fallback, "blocks": blocks}


class SlackService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._db = db
        self._settings = settings
        self._client = client  # injectable for tests (httpx.MockTransport)

    async def post(self, incident_id, kind: str, message: dict[str, Any]) -> SlackMessage:
        webhook_url = self._settings.slack_webhook_url
        row = SlackMessage(
            incident_id=incident_id,
            kind=kind,
            channel=message["channel"],
            text=message["text"],
            blocks=message["blocks"],
            transport="slack_webhook" if webhook_url else "mock",
            delivered=not webhook_url,  # mock mode: stored == delivered
        )

        if webhook_url:
            try:
                await self._deliver(webhook_url, message)
                row.delivered = True
            except Exception as exc:
                row.delivered = False
                row.delivery_error = f"{type(exc).__name__}: {exc}"
                logger.warning("slack delivery failed for incident %s: %s", incident_id, exc)

        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def _deliver(self, url: str, message: dict[str, Any]) -> None:
        payload = {"text": message["text"], "blocks": message["blocks"]}
        if self._client is not None:
            resp = await self._client.post(url, json=payload)
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
        resp.raise_for_status()
