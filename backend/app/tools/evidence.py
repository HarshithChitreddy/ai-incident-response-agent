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


async def search_logs(
    ctx: ToolContext,
    service: str,
    query: str = "",
    level: str | None = None,
    limit: int = 20,
) -> list[dict]:
    logs = json.loads((ctx.settings.data_dir / "sample_logs.json").read_text())
    needle = query.lower()
    hits = [
        entry
        for entry in logs
        if entry["service"] == service
        and (not level or entry["level"] == level.upper())
        and (not needle or needle in entry["message"].lower())
    ]
    hits.sort(key=lambda entry: entry["timestamp"])
    return hits[:limit]
