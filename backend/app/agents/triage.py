"""LangGraph triage workflow.

Two nodes in a ReAct loop — `agent` (LLM decides) and `tools` (we execute) —
with a conditional edge that exits when the model stops requesting tools or
the iteration budget runs out. Nodes close over a TriageContext instead of
stuffing live objects (db session, llm client) into graph state, which keeps
the state a plain serializable dict.

The LLM node talks to our LLMClient seam directly, not a LangChain chat model:
that's what makes MOCK_LLM work identically here.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.trace import AgentTracer, jsonable
from app.models import Incident
from app.services.llm import LLMClient
from app.tools.base import ToolContext
from app.tools.registry import anthropic_tool_defs, dispatch

MAX_ITERATIONS = 12

SYSTEM_PROMPT = """\
You are an incident triage agent for a production microservices platform.

Investigate the alert by gathering evidence with your tools: recent commits, logs,
metrics, the matching runbook, similar historical incidents, a severity prediction,
and a ranking of likely root-cause commits. Weigh evidence like an SRE: correlate
deploy times against metric inflection points, and treat "the last deploy did it"
as a hypothesis to verify, not a conclusion.

When you have enough evidence, respond with ONLY a JSON object (no prose, no code
fences) with these keys:
- root_cause: string — most likely root cause and the evidence behind it
- why_it_might_be_wrong: string — the strongest argument against your own conclusion
- competing_candidates: array of {commit, reason, likelihood} — other plausible causes
- confidence: number between 0 and 1
- severity: one of "critical", "high", "medium", "low"
- user_impact: string — who is affected and how badly
- recommended_runbook_steps: array of strings — concrete next actions
"""

VALID_SEVERITIES = {"critical", "high", "medium", "low", "warning"}


class TriageState(TypedDict):
    messages: list[dict[str, Any]]
    iterations: int
    done: bool
    final_text: str


@dataclass
class TriageContext:
    tool_ctx: ToolContext
    llm: LLMClient
    tracer: AgentTracer


def incident_prompt(incident: Incident) -> str:
    return (
        "A production alert has fired. Investigate it, then produce your final JSON analysis.\n\n"
        f"alertname: {incident.alertname}\n"
        f"service: {incident.service}\n"
        f"label_severity: {incident.severity}\n"
        f"started_at: {incident.started_at.isoformat()}\n"
        f"title: {incident.title}\n"
        f"description: {incident.description}\n"
        f"labels: {json.dumps(incident.labels)}\n"
    )


def parse_analysis(text: str) -> dict[str, Any]:
    """Extract the analysis JSON, tolerating fences and surrounding prose."""
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first : last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed

    return {
        "root_cause": text.strip() or "No analysis produced",
        "confidence": None,
        "parse_error": True,
    }
