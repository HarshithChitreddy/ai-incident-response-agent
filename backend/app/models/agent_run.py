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


class TraceStep(Base):
    """One step of an agent run: an LLM call or a tool call, with its full
    input and output. This is the dashboard's reasoning timeline."""

    __tablename__ = "agent_trace_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int]
    step_type: Mapped[str] = mapped_column(String(32))  # llm_call | tool_call
    name: Mapped[str] = mapped_column(String(128))
    input: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    output: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="steps")
