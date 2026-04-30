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

        try:
            analysis = await run_triage_graph(ctx, incident)

            brief = await generate_slack_brief(llm, incident, analysis)
            await tracer.record(
                "llm_call",
                "generate_slack_brief",
                {"incident_id": str(incident.id)},
                {"text": brief.text},
                tokens_in=brief.usage.get("input_tokens", 0),
                tokens_out=brief.usage.get("output_tokens", 0),
            )
            analysis["slack_brief"] = brief.text

            predicted = analysis.get("severity")
            if predicted in VALID_SEVERITIES:
                incident.severity = predicted

            slack = SlackService(db, settings)
            message = await slack.post(
                incident.id, "incident_opened", build_incident_opened_message(incident, analysis)
            )
            run.result = analysis
            run.status = "completed"
            run.finished_at = utcnow()
            await db.commit()
        except Exception as exc:
            logger.exception("triage run %s failed", run.id)
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished_at = utcnow()
            await db.commit()


async def run_postmortem_for_incident(
    incident_id,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    llm: LLMClient | None = None,
) -> None:
    factory = session_factory or _default_factory()
    llm = llm or get_llm_client()

    async with factory() as db:
        incident = await db.scalar(
            select(Incident).options(selectinload(Incident.events)).where(Incident.id == incident_id)
        )
        if incident is None:
            logger.warning("postmortem requested for unknown incident %s", incident_id)
            return

        # idempotent: resolving twice must not produce two postmortems
        existing = await db.scalar(
            select(AgentRun).where(
                AgentRun.incident_id == incident.id,
                AgentRun.kind == "postmortem",
                AgentRun.status == "completed",
            )
        )
        if existing is not None:
            return

        analysis = await _latest_analysis(db, incident) or {
            "root_cause": "No automated analysis was completed for this incident."
        }

        timeline = [{"at": incident.started_at.isoformat(), "event": "alert fired, incident opened"}]
        timeline += [
            {"at": e.received_at.isoformat(), "event": f"alert {e.status} notification received"}
            for e in incident.events
        ]
        if incident.resolved_at:
            timeline.append({"at": incident.resolved_at.isoformat(), "event": "incident resolved"})

        run = AgentRun(incident_id=incident.id, kind="postmortem", model=getattr(llm, "model", ""))
        db.add(run)
        await db.commit()
        await db.refresh(run)
        tracer = AgentTracer(db, run)

        try:
            resp = await generate_postmortem(llm, incident, analysis, timeline)
            await tracer.record(
                "llm_call",
                "generate_postmortem",
                {"incident_id": str(incident.id)},
                {"text": resp.text},
                tokens_in=resp.usage.get("input_tokens", 0),
                tokens_out=resp.usage.get("output_tokens", 0),
            )
            slack = SlackService(db, get_settings())
            message = await slack.post(
                incident.id,
                "incident_resolved",
                build_incident_resolved_message(incident, postmortem_ready=True),
            )
            await tracer.record(
                "notification",
                "post_slack_message",
                {"kind": "incident_resolved", "channel": message.channel},
                {
                    "transport": message.transport,
                    "delivered": message.delivered,
                    "message_id": str(message.id),
                },
            )

            run.result = {"markdown": resp.text}
            run.status = "completed"
            run.finished_at = utcnow()
            await db.commit()
        except Exception as exc:
            logger.exception("postmortem run %s failed", run.id)
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished_at = utcnow()
            await db.commit()


async def _latest_analysis(db: AsyncSession, incident: Incident) -> dict | None:
    run = await db.scalar(
        select(AgentRun)
        .where(
            AgentRun.incident_id == incident.id,
            AgentRun.kind == "triage",
            AgentRun.status == "completed",
        )
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    return run.result if run else None
