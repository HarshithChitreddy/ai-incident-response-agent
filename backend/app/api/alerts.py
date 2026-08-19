from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.runner import run_postmortem_for_incident, run_triage_for_incident
from app.db.session import get_db, get_session_factory
from app.schemas.alert import AlertmanagerWebhook
from app.schemas.incident import WebhookIngestResult
from app.services.incident_service import ingest_webhook

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("/webhook", status_code=202, response_model=WebhookIngestResult)
async def receive_alert_webhook(
    payload: AlertmanagerWebhook,
    db: AsyncSession = Depends(get_db),
) -> WebhookIngestResult:
    """Entry point for Alertmanager-compatible alerts (real or simulated)."""
    return await ingest_webhook(db, payload)
