"""Alert ingestion: turn Alertmanager webhook deliveries into incidents.

Deduplication contract: an alert's fingerprint identifies one failing condition.
While an incident for that fingerprint is open, further firings attach an
AlertEvent instead of opening a duplicate; a resolved notification closes it.
"""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertEvent, Incident, utcnow
from app.schemas.alert import AlertmanagerAlert, AlertmanagerWebhook
from app.schemas.incident import WebhookIngestResult

OPEN_STATUSES = ("open", "acknowledged")


def compute_fingerprint(alert: AlertmanagerAlert) -> str:
    if alert.fingerprint:
        return alert.fingerprint
    canonical = json.dumps(alert.labels, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


async def find_open_incident(db: AsyncSession, fingerprint: str) -> Incident | None:
    stmt = (
        select(Incident)
        .where(Incident.fingerprint == fingerprint, Incident.status.in_(OPEN_STATUSES))
        .order_by(Incident.created_at.desc())
        .limit(1)
    )
    return await db.scalar(stmt)


def _incident_from_alert(alert: AlertmanagerAlert, fingerprint: str) -> Incident:
    alertname = alert.labels.get("alertname", "UnknownAlert")
    service = alert.labels.get("service") or alert.labels.get("job") or "unknown"
    return Incident(
        fingerprint=fingerprint,
        alertname=alertname,
        service=service,
        severity=alert.labels.get("severity", "warning"),
        title=alert.annotations.get("summary") or f"{alertname} on {service}",
        description=alert.annotations.get("description", ""),
        labels=alert.labels,
        annotations=alert.annotations,
        started_at=alert.starts_at,
    )


def _event_from_alert(incident: Incident, alert: AlertmanagerAlert) -> AlertEvent:
    return AlertEvent(
        incident=incident,
        status=alert.status,
        payload=alert.model_dump(mode="json", by_alias=True),
    )


async def ingest_webhook(db: AsyncSession, payload: AlertmanagerWebhook) -> WebhookIngestResult:
    result = WebhookIngestResult(created=[], updated=[], resolved=[], ignored=0)

    for alert in payload.alerts:
        fingerprint = compute_fingerprint(alert)
        incident = await find_open_incident(db, fingerprint)

        if alert.status == "firing":
            if incident is None:
                incident = _incident_from_alert(alert, fingerprint)
                db.add(incident)
                await db.flush()
                result.created.append(incident.id)
            else:
                incident.updated_at = utcnow()
                result.updated.append(incident.id)
            db.add(_event_from_alert(incident, alert))
        else:  # resolved
            if incident is None:
                # resolved notification for something we never opened
                result.ignored += 1
                continue
            incident.status = "resolved"
            # Alertmanager's zero value for endsAt is year 1 — treat it as unset
            ends = alert.ends_at
            incident.resolved_at = ends if ends is not None and ends.year > 1 else utcnow()
            db.add(_event_from_alert(incident, alert))
            result.resolved.append(incident.id)

    await db.commit()
    return result
