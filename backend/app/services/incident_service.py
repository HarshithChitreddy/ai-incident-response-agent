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
