"""LLM-backed generation steps: Slack brief and postmortem.

These are invoked deterministically by the agent runner (every triage produces
a brief; every resolution produces a postmortem) rather than left to the
model's tool choice — you never want an incident without them.
"""

import json
from typing import Any

from app.models import Incident
from app.services.llm import LLMClient, LLMResponse

_SLACK_SYSTEM = (
    "You write Slack incident briefs for an engineering on-call channel. "
    "Use Slack markdown (*bold*, emoji shortcodes like :rotating_light:). "
    "Keep it under 12 lines: a status headline, what we know, the likely cause "
    "with confidence, user impact, and the immediate next step. No preamble."
)

_POSTMORTEM_SYSTEM = (
    "You write blameless engineering postmortems in Markdown. Structure: "
    "# Postmortem title, then sections: ## Summary, ## Timeline (UTC), ## Root Cause, "
    "## Impact, ## Resolution, ## Action Items (numbered), ## Prevention. "
    "Be specific and factual; use only the evidence provided. No preamble."
)

_ANALYSIS_KEYS = (
    "root_cause",
    "why_it_might_be_wrong",
    "competing_candidates",
    "confidence",
    "severity",
    "user_impact",
    "recommended_runbook_steps",
)


def _incident_context(incident: Incident) -> dict[str, Any]:
    return {
        "alertname": incident.alertname,
        "service": incident.service,
        "severity": incident.severity,
        "status": incident.status,
        "title": incident.title,
        "description": incident.description,
        "started_at": incident.started_at.isoformat(),
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
    }


async def generate_slack_brief(
    llm: LLMClient, incident: Incident, analysis: dict[str, Any]
) -> LLMResponse:
    payload = {
        "incident": _incident_context(incident),
        "analysis": {k: analysis.get(k) for k in _ANALYSIS_KEYS},
    }
    return await llm.create_message(
        system=_SLACK_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Write the Slack brief for this incident:\n{json.dumps(payload, default=str)}",
            }
        ],
    )


async def generate_postmortem(
    llm: LLMClient,
    incident: Incident,
    analysis: dict[str, Any],
    timeline: list[dict[str, Any]],
) -> LLMResponse:
    payload = {
        "incident": _incident_context(incident),
        "analysis": {k: analysis.get(k) for k in _ANALYSIS_KEYS},
        "timeline": timeline,
    }
    return await llm.create_message(
        system=_POSTMORTEM_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Write the postmortem for this resolved incident:\n{json.dumps(payload, default=str)}",
            }
        ],
    )
