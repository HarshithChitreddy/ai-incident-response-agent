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
