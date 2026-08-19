import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.incident import JSONVariant


class SlackMessage(Base):
    """Every outgoing Slack message, stored verbatim. In mock mode (no webhook
    URL) storage *is* delivery; with a real webhook this doubles as the audit
    log and the dashboard's channel view."""

    __tablename__ = "slack_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # incident_opened | incident_resolved
    channel: Mapped[str] = mapped_column(String(64), default="#incidents")
    text: Mapped[str] = mapped_column(Text)  # notification fallback text
    blocks: Mapped[list] = mapped_column(JSONVariant, default=list)  # Slack Block Kit
    transport: Mapped[str] = mapped_column(String(16), default="mock")  # mock | slack_webhook
    delivered: Mapped[bool] = mapped_column(default=True)
    delivery_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
