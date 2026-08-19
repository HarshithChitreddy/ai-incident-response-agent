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

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z][a-z0-9]+")
_STOPWORDS = {"the", "and", "for", "with", "this", "that", "runbook", "alert"}


def _tokens(text: str) -> set[str]:
    # split CamelCase (HighErrorRate -> high error rate) before tokenizing
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return {t for t in _WORD_RE.findall(spaced.lower()) if t not in _STOPWORDS}


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


async def query_metrics(ctx: ToolContext, service: str) -> dict:
    df = pd.read_csv(ctx.settings.data_dir / "sample_metrics.csv")
    df = df[df["service"] == service].sort_values("timestamp")
    if df.empty:
        return {"service": service, "series": [], "summary": {}, "note": "no metrics for service"}

    numeric_cols = [c for c in df.columns if c not in ("timestamp", "service")]
    summary = {}
    for col in numeric_cols:
        baseline = float(df[col].head(3).mean())
        current = float(df[col].tail(3).mean())
        delta_pct = ((current - baseline) / baseline * 100) if baseline else None
        summary[col] = {
            "baseline": round(baseline, 2),
            "current": round(current, 2),
            "delta_pct": round(delta_pct, 1) if delta_pct is not None else None,
        }
    return {
        "service": service,
        "window": {"from": df["timestamp"].iloc[0], "to": df["timestamp"].iloc[-1]},
        "summary": summary,
        "series": df.to_dict(orient="records"),
    }


async def retrieve_runbook(ctx: ToolContext, query: str) -> dict:
    """Semantic retrieval over the runbook library (ChromaDB + MiniLM), falling
    back to keyword matching if the vector store is unavailable."""
    from app.rag.store import get_runbook_index  # deferred: chromadb import is heavy

    index = ctx.runbook_index or get_runbook_index()
    try:
        chunks = await index.search(query, k=4)
    except Exception:
        logger.exception("vector retrieval failed; falling back to keyword matching")
        chunks = []
    if not chunks:
        return await _keyword_retrieve_runbook(ctx, query)

    best = chunks[0]
    return {
        "runbook": best.source,
        "retriever": "chroma/all-MiniLM-L6-v2",
        "match_score": best.score,
        "matched_sections": [
            {
                "source": c.source,
                "section": c.section,
                "score": c.score,
                "excerpt": c.content[:400],
            }
            for c in chunks
        ],
        "content": (index.runbooks_dir / best.source).read_text(),
    }


async def _keyword_retrieve_runbook(ctx: ToolContext, query: str) -> dict:
    """Phase 2 keyword matcher, kept as the degraded-mode path."""
    query_tokens = _tokens(query)
    best_name, best_score, best_content = None, -1.0, ""

    for path in sorted((ctx.settings.data_dir / "runbooks").glob("*.md")):
        content = path.read_text()
        title = content.splitlines()[0] if content else ""
        # title matches count 3x — the title names the alert class
        score = 3 * len(query_tokens & _tokens(title + " " + path.stem)) + len(
            query_tokens & _tokens(content)
        )
        if score > best_score:
            best_name, best_score, best_content = path.name, score, content

    return {
        "runbook": best_name,
        "match_score": best_score,
        "retriever": "keyword-fallback",
        "content": best_content,
    }


async def find_similar_incidents(
    ctx: ToolContext,
    service: str,
    alertname: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Past incidents from Postgres — same alert class first, same service second."""
    stmt = select(HistoricalIncident).limit(50)
    if alertname:
        stmt = stmt.where(
            or_(HistoricalIncident.alertname == alertname, HistoricalIncident.service == service)
        )
    else:
        stmt = stmt.where(HistoricalIncident.service == service)

    rows = (await ctx.db.scalars(stmt)).all()
    # exact alertname+service matches are the most informative
    rows = sorted(
        rows,
        key=lambda r: (r.alertname == alertname, r.service == service),
        reverse=True,
    )[:limit]
    return [
        {
            "service": r.service,
            "alertname": r.alertname,
            "severity": r.severity,
            "root_cause": r.root_cause,
            "deploy_within_hour": r.deploy_within_hour,
            "time_to_resolve_min": r.time_to_resolve_min,
            "summary": r.summary,
        }
        for r in rows
    ]
