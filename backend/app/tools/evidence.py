"""Evidence-gathering tools. Commits, logs, and metrics read from the files in
data/ — they stand in for the git host, log store, and metrics store, so the
tools have the same shape they'd have against real systems. Similar incidents
come from Postgres. Runbook retrieval is semantic (ChromaDB, see app/rag/)
with the Phase 2 keyword matcher retained as an offline fallback.
"""

import json
import logging
import re

import pandas as pd
from sqlalchemy import or_, select

from app.models import HistoricalIncident
from app.tools.base import ToolContext


async def get_recent_commits(ctx: ToolContext, service: str, limit: int = 10) -> list[dict]:
    commits = json.loads((ctx.settings.data_dir / "sample_commits.json").read_text())
    relevant = [c for c in commits if c["service"] in (service, "platform")]
    relevant.sort(key=lambda c: c["timestamp"], reverse=True)
    return relevant[:limit]
