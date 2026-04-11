import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TraceStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seq: int
    step_type: str
    name: str
    input: dict
    output: dict
    tokens_in: int
    tokens_out: int
    created_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    kind: str
    status: str
    model: str
    result: dict
    error: str
    started_at: datetime
    finished_at: datetime | None


class AnalysisOut(BaseModel):
    run_id: uuid.UUID
    model: str
    finished_at: datetime | None
    analysis: dict


class PostmortemOut(BaseModel):
    run_id: uuid.UUID
    finished_at: datetime | None
    markdown: str
