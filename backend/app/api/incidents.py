import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agents.runner import run_postmortem_for_incident
from app.db.session import get_db, get_session_factory
from app.models import AgentRun, Incident, SlackMessage, utcnow
from app.schemas.agent import AgentRunOut, AnalysisOut, PostmortemOut, TraceStepOut
from app.schemas.incident import IncidentDetailOut, IncidentOut
from app.schemas.slack import SlackMessageOut

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentOut])
async def list_incidents(
    status: str | None = Query(default=None, description="Filter: open | acknowledged | resolved"),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[Incident]:
    stmt = select(Incident).order_by(Incident.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Incident.status == status)
    return list((await db.scalars(stmt)).all())


@router.get("/{incident_id}", response_model=IncidentDetailOut)
async def get_incident(incident_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Incident:
    stmt = (
        select(Incident)
        .options(selectinload(Incident.events))
        .where(Incident.id == incident_id)
    )
    incident = await db.scalar(stmt)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.post("/{incident_id}/resolve", response_model=IncidentOut)
async def resolve_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Incident:
    """Manually resolve an incident."""
    incident = await db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.status != "resolved":
        incident.status = "resolved"
        incident.resolved_at = utcnow()
        await db.commit()
        await db.refresh(incident)
    return incident


@router.get("/{incident_id}/analysis", response_model=AnalysisOut)
async def get_analysis(incident_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AnalysisOut:
    run = await _latest_run(db, incident_id, kind="triage", status="completed")
    if run is None:
        raise HTTPException(status_code=404, detail="No completed analysis for this incident yet")
    return AnalysisOut(run_id=run.id, model=run.model, finished_at=run.finished_at, analysis=run.result)


async def _latest_run(
    db: AsyncSession, incident_id: uuid.UUID, *, kind: str, status: str
) -> AgentRun | None:
    stmt = (
        select(AgentRun)
        .where(
            AgentRun.incident_id == incident_id,
            AgentRun.kind == kind,
            AgentRun.status == status,
        )
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    return await db.scalar(stmt)
