"""Agent run orchestration: entry points scheduled as FastAPI background tasks.

Background tasks outlive the request, so each run opens its own session from
the factory it was handed (the webhook passes it via dependency injection,
which is what lets tests swap in SQLite).
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agents.trace import AgentTracer
from app.agents.triage import VALID_SEVERITIES, TriageContext, run_triage_graph
from app.config import Settings, get_settings
from app.models import AgentRun, Incident, utcnow
from app.services.llm import LLMClient, get_llm_client
from app.services.slack import (
    SlackService,
    build_incident_opened_message,
    build_incident_resolved_message,
)
from app.tools.base import ToolContext
from app.tools.generation import generate_postmortem, generate_slack_brief

logger = logging.getLogger(__name__)


def _default_factory() -> async_sessionmaker[AsyncSession]:
    from app.db.session import async_session_factory

    return async_session_factory


async def run_triage_for_incident(
    incident_id,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    llm: LLMClient | None = None,
    settings: Settings | None = None,
    runbook_index=None,
) -> None:
    """`settings` and `runbook_index` are injectable so the eval harness can
    point the agent at a per-case evidence world; production callers omit them."""
    factory = session_factory or _default_factory()
    llm = llm or get_llm_client()
    settings = settings or get_settings()

    async with factory() as db:
        incident = await db.get(Incident, incident_id)
        if incident is None:
            logger.warning("triage requested for unknown incident %s", incident_id)
            return

        run = AgentRun(incident_id=incident.id, kind="triage", model=getattr(llm, "model", ""))
        db.add(run)
        await db.commit()
        await db.refresh(run)

        tracer = AgentTracer(db, run)
        ctx = TriageContext(
            tool_ctx=ToolContext(db=db, settings=settings, runbook_index=runbook_index),
            llm=llm,
            tracer=tracer,
        )

        analysis = await run_triage_graph(ctx, incident)

        run.result = analysis
        run.status = "completed"
        run.finished_at = utcnow()
        await db.commit()

