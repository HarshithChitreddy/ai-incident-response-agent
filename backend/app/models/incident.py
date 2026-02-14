import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

# JSONB on Postgres, plain JSON elsewhere (keeps the SQLite test harness working)
JSONVariant = JSON().with_variant(JSONB(), "postgresql")
