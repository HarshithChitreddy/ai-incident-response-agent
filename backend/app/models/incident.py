import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

# JSONB on Postgres, plain JSON elsewhere (keeps the SQLite test harness working)
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class Incident(Base):
    """One logical incident. Repeated firings of the same alert (same fingerprint)
    attach AlertEvents to the existing open incident instead of creating a new one."""

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    alertname: Mapped[str] = mapped_column(String(255))
    service: Mapped[str] = mapped_column(String(255), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    labels: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    annotations: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="AlertEvent.received_at",
    )


class AlertEvent(Base):
    """Raw alert payload received for an incident — the audit trail of every
    firing/resolved notification, kept verbatim for the agent and the dashboard."""

    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="events")
