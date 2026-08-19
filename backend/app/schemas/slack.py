import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SlackMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    kind: str
    channel: str
    text: str
    blocks: list
    transport: str
    delivered: bool
    delivery_error: str
    created_at: datetime
