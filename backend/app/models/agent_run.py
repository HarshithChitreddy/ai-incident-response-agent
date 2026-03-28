import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow
from app.models.incident import JSONVariant


class AgentRun(Base):
    """One agent execution against an incident: a triage investigation or a
    postmortem generation. `result` holds the structured output (analysis JSON
    with slack_brief, or {"markdown": ...} for postmortems)."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # triage | postmortem
    status: Mapped[str] = mapped_column(String(32), default="running")  # running | completed | failed
    model: Mapped[str] = mapped_column(String(128), default="")
    result: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    steps: Mapped[list["TraceStep"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="TraceStep.seq",
    )
