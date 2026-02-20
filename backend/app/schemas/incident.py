import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    payload: dict
    received_at: datetime


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fingerprint: str
    alertname: str
    service: str
    severity: str
    status: str
    title: str
    description: str
    labels: dict
    annotations: dict
    started_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IncidentDetailOut(IncidentOut):
    events: list[AlertEventOut]
